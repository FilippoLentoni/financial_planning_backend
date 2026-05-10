import * as path from 'path';
import {
  Duration,
  RemovalPolicy,
  aws_dynamodb as dynamodb,
  aws_lambda as lambda,
  aws_logs as logs,
} from 'aws-cdk-lib';
import { Construct } from 'constructs';

export interface ToolsResourcesProps {
  readonly stageName: string;
  readonly removalPolicy: RemovalPolicy;
}

export interface ToolsResources {
  readonly stateTable: dynamodb.Table;
  readonly toolFunction: lambda.Function;
}

export function createToolsResources(
  scope: Construct,
  props: ToolsResourcesProps,
): ToolsResources {
  const stateTable = new dynamodb.Table(scope, 'GatewayStateTable', {
    partitionKey: { name: 'id', type: dynamodb.AttributeType.STRING },
    billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
    timeToLiveAttribute: 'ttl',
    removalPolicy: props.removalPolicy,
  });

  const toolLogGroup = new logs.LogGroup(scope, 'ToolLogGroup', {
    retention: logs.RetentionDays.ONE_MONTH,
    removalPolicy: props.removalPolicy,
  });

  const toolFunction = new lambda.Function(scope, 'ToolFunction', {
    runtime: lambda.Runtime.PYTHON_3_11,
    architecture: lambda.Architecture.ARM_64,
    handler: 'index.handler',
    code: lambda.Code.fromAsset(path.join(__dirname, '..', 'lambda', 'tools')),
    timeout: Duration.seconds(10),
    memorySize: 256,
    logGroup: toolLogGroup,
    environment: {
      STAGE: props.stageName,
      STATE_TABLE_NAME: stateTable.tableName,
    },
  });

  stateTable.grantReadWriteData(toolFunction);

  return {
    stateTable,
    toolFunction,
  };
}
