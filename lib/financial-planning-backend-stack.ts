import * as path from 'path';
import {
  CfnOutput,
  Duration,
  RemovalPolicy,
  SecretValue,
  Stack,
  StackProps,
  aws_apigateway as apigateway,
  aws_iam as iam,
  aws_ecr_assets as ecrAssets,
  aws_lambda as lambda,
  aws_logs as logs,
  aws_s3 as s3,
  aws_s3_deployment as s3deploy,
  aws_secretsmanager as secretsmanager,
} from 'aws-cdk-lib';
import {
  AgentRuntimeArtifact,
  ProtocolType,
  Runtime,
  RuntimeAuthorizerConfiguration,
  RuntimeNetworkConfiguration,
} from '@aws-cdk/aws-bedrock-agentcore-alpha';
import { Construct } from 'constructs';
import { DEFAULT_JUDGE_MODEL_ID, DEFAULT_MODEL_ID, StageConfig } from './config';
import { createGatewayResources } from './gateway-construct';
import { createToolsResources } from './tools-construct';

export interface FinancialPlanningBackendStackProps extends StackProps {
  readonly stage: StageConfig;
}

export class FinancialPlanningBackendStack extends Stack {
  constructor(scope: Construct, id: string, props: FinancialPlanningBackendStackProps) {
    super(scope, id, props);

    const removalPolicy =
      props.stage.removalPolicy === 'destroy' ? RemovalPolicy.DESTROY : RemovalPolicy.RETAIN;

    const dataBucket = new s3.Bucket(this, 'EvalDataBucket', {
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
      enforceSSL: true,
      removalPolicy,
      autoDeleteObjects: props.stage.removalPolicy === 'destroy',
      lifecycleRules: [{ expiration: Duration.days(30) }],
    });

    new s3deploy.BucketDeployment(this, 'SampleEvalData', {
      sources: [s3deploy.Source.asset(path.join(__dirname, '..', 'test-data'))],
      destinationBucket: dataBucket,
      destinationKeyPrefix: 'sample-eval',
      retainOnDelete: props.stage.removalPolicy !== 'destroy',
    });

    const tools = createToolsResources(this, {
      stageName: props.stage.name,
      removalPolicy,
    });

    const runtimeRole = new iam.Role(this, 'AgentRuntimeRole', {
      assumedBy: new iam.ServicePrincipal('bedrock-agentcore.amazonaws.com').withConditions({
        StringEquals: {
          'aws:SourceAccount': this.account,
        },
        ArnLike: {
          'aws:SourceArn': `arn:aws:bedrock-agentcore:${this.region}:${this.account}:runtime/*`,
        },
      }),
      description: 'Execution role for the public AgentCore runtime.',
    });

    runtimeRole.addToPolicy(
      new iam.PolicyStatement({
        actions: [
          'bedrock:InvokeModel',
          'bedrock:InvokeModelWithResponseStream',
          'cloudwatch:PutMetricData',
          'logs:CreateLogGroup',
          'logs:CreateLogStream',
          'logs:DescribeLogGroups',
          'logs:DescribeLogStreams',
          'logs:PutLogEvents',
        ],
        resources: ['*'],
      }),
    );
    tools.toolFunction.grantInvoke(runtimeRole);
    dataBucket.grantReadWrite(runtimeRole);

    const langfuseSecret = new secretsmanager.Secret(this, 'LangfusePlaceholderSecret', {
      description:
        'Optional Langfuse credentials for evaluator/runtime observability. Replace values before enabling Langfuse.',
      secretObjectValue: {
        LANGFUSE_PUBLIC_KEY: SecretValue.unsafePlainText('replace-me'),
        LANGFUSE_SECRET_KEY: SecretValue.unsafePlainText('replace-me'),
        LANGFUSE_HOST: SecretValue.unsafePlainText('https://cloud.langfuse.com'),
      },
      removalPolicy,
    });
    langfuseSecret.grantRead(runtimeRole);

    const runtime = new Runtime(this, 'AgentRuntime', {
      runtimeName: props.stage.runtimeName,
      description: `Financial planning AgentCore runtime for ${props.stage.name}.`,
      executionRole: runtimeRole,
      agentRuntimeArtifact: AgentRuntimeArtifact.fromAsset(path.join(__dirname, '..', 'agent'), {
        platform: ecrAssets.Platform.LINUX_ARM64,
      }),
      networkConfiguration: RuntimeNetworkConfiguration.usingPublicNetwork(),
      protocolConfiguration: ProtocolType.HTTP,
      authorizerConfiguration: RuntimeAuthorizerConfiguration.usingIAM(),
      environmentVariables: {
        STAGE: props.stage.name,
        AWS_REGION: this.region,
        MODEL_ID: DEFAULT_MODEL_ID,
        TOOL_FUNCTION_NAME: tools.toolFunction.functionName,
        EVAL_BUCKET: dataBucket.bucketName,
        LANGFUSE_SECRET_ARN: langfuseSecret.secretArn,
      },
      tags: {
        stage: props.stage.name,
        app: 'financial-planning-backend',
      },
    });

    const runtimeProxyLogGroup = new logs.LogGroup(this, 'RuntimeProxyLogGroup', {
      retention: logs.RetentionDays.ONE_MONTH,
      removalPolicy,
    });

    const runtimeProxyFn = new lambda.Function(this, 'RuntimeProxyFunction', {
      runtime: lambda.Runtime.PYTHON_3_11,
      architecture: lambda.Architecture.ARM_64,
      handler: 'index.handler',
      code: lambda.Code.fromAsset(path.join(__dirname, '..', 'lambda', 'runtime-proxy')),
      timeout: Duration.seconds(30),
      memorySize: 512,
      logGroup: runtimeProxyLogGroup,
      environment: {
        ALLOWED_RUNTIME_PATTERN: `^${props.stage.runtimeName}`,
        CORS_ALLOWED_ORIGINS: process.env.CORS_ALLOWED_ORIGINS ?? '*',
      },
    });
    runtimeProxyFn.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ['bedrock-agentcore:InvokeAgentRuntime'],
        resources: [runtime.agentRuntimeArn, `${runtime.agentRuntimeArn}/runtime-endpoint/*`],
      }),
    );
    runtimeProxyFn.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ['sts:GetCallerIdentity'],
        resources: ['*'],
      }),
    );

    const api = new apigateway.RestApi(this, 'RuntimeApi', {
      restApiName: `financial-planning-backend-${props.stage.name}`,
      deployOptions: {
        stageName: props.stage.name,
        tracingEnabled: true,
      },
      defaultCorsPreflightOptions: {
        allowOrigins: apigateway.Cors.ALL_ORIGINS,
        allowMethods: ['POST', 'OPTIONS'],
        allowHeaders: [
          'Content-Type',
          'Authorization',
          'X-Amz-Date',
          'X-Api-Key',
          'X-Amz-Security-Token',
          'X-Amz-Content-Sha256',
        ],
      },
    });
    const runtimeResource = api.root.addResource('runtime');
    const invokeResource = runtimeResource.addResource('invoke');
    invokeResource.addMethod('POST', new apigateway.LambdaIntegration(runtimeProxyFn), {
      authorizationType: apigateway.AuthorizationType.IAM,
    });

    const gateway = createGatewayResources(this, {
      api,
      toolFunction: tools.toolFunction,
      removalPolicy,
    });

    new CfnOutput(this, 'RuntimeArn', { value: runtime.agentRuntimeArn });
    new CfnOutput(this, 'RuntimeName', { value: runtime.agentRuntimeName });
    new CfnOutput(this, 'BackendApiUrl', { value: api.url });
    new CfnOutput(this, 'RuntimeInvokeUrl', { value: `${api.url}runtime/invoke` });
    new CfnOutput(this, 'GatewaysUrl', { value: gateway.gatewaysUrl });
    new CfnOutput(this, 'McpProxyUrl', { value: gateway.mcpProxyUrl });
    new CfnOutput(this, 'ToolFunctionName', { value: tools.toolFunction.functionName });
    new CfnOutput(this, 'GatewayStateTableName', { value: tools.stateTable.tableName });
    new CfnOutput(this, 'EvalDataBucketName', { value: dataBucket.bucketName });
    new CfnOutput(this, 'LangfuseSecretArn', { value: langfuseSecret.secretArn });
    new CfnOutput(this, 'SmokeTestCommand', {
      value: [
        'python -m financial_planning_tests.ping_agent',
        `--runtime-arn ${runtime.agentRuntimeArn}`,
        `--region ${this.region}`,
        '--prompt health',
      ].join(' '),
    });
    new CfnOutput(this, 'EvalCommand', {
      value: [
        'python -m financial_planning_tests.run_eval',
        `--runtime-arn ${runtime.agentRuntimeArn}`,
        `--region ${this.region}`,
        `--judge-model ${DEFAULT_JUDGE_MODEL_ID}`,
        '--dataset test-data/sample_eval.jsonl',
        '--min-score 0.5',
      ].join(' '),
    });
  }
}
