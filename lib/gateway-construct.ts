import * as path from 'path';
import {
  Duration,
  RemovalPolicy,
  aws_apigateway as apigateway,
  aws_lambda as lambda,
  aws_logs as logs,
} from 'aws-cdk-lib';
import { Construct } from 'constructs';

export interface GatewayResourcesProps {
  readonly api: apigateway.RestApi;
  readonly toolFunction: lambda.Function;
  readonly removalPolicy: RemovalPolicy;
}

export interface GatewayResources {
  readonly gatewayProxyFunction: lambda.Function;
  readonly gatewaysUrl: string;
  readonly mcpProxyUrl: string;
}

export function createGatewayResources(
  scope: Construct,
  props: GatewayResourcesProps,
): GatewayResources {
  const gatewayProxyLogGroup = new logs.LogGroup(scope, 'GatewayProxyLogGroup', {
    retention: logs.RetentionDays.ONE_MONTH,
    removalPolicy: props.removalPolicy,
  });

  const gatewayProxyFunction = new lambda.Function(scope, 'GatewayProxyFunction', {
    runtime: lambda.Runtime.PYTHON_3_11,
    architecture: lambda.Architecture.ARM_64,
    handler: 'index.handler',
    code: lambda.Code.fromAsset(path.join(__dirname, '..', 'lambda', 'gateway-proxy')),
    timeout: Duration.seconds(20),
    memorySize: 256,
    logGroup: gatewayProxyLogGroup,
    environment: {
      TOOL_FUNCTION_NAME: props.toolFunction.functionName,
      CORS_ALLOWED_ORIGINS: process.env.CORS_ALLOWED_ORIGINS ?? '*',
    },
  });

  props.toolFunction.grantInvoke(gatewayProxyFunction);

  const gatewaysResource = props.api.root.addResource('gateways');
  const gatewaysIamResource = gatewaysResource.addResource('iam');
  gatewaysIamResource.addMethod('GET', new apigateway.LambdaIntegration(gatewayProxyFunction), {
    authorizationType: apigateway.AuthorizationType.IAM,
  });

  const mcpResource = props.api.root.addResource('mcp');
  const mcpProxyResource = mcpResource.addResource('proxy');
  mcpProxyResource.addMethod('POST', new apigateway.LambdaIntegration(gatewayProxyFunction), {
    authorizationType: apigateway.AuthorizationType.IAM,
  });

  return {
    gatewayProxyFunction,
    gatewaysUrl: `${props.api.url}gateways/iam`,
    mcpProxyUrl: `${props.api.url}mcp/proxy`,
  };
}
