import * as path from 'path';
import {
  Duration,
  RemovalPolicy,
  aws_dynamodb as dynamodb,
  aws_events as events,
  aws_events_targets as targets,
  aws_lambda as lambda,
  aws_logs as logs,
} from 'aws-cdk-lib';
import { Construct } from 'constructs';

export interface ToolsResourcesProps {
  readonly stageName: string;
  readonly removalPolicy: RemovalPolicy;
  readonly modelId: string;
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
    code: lambda.Code.fromAsset(path.join(__dirname, '..', 'lambda', 'tools'), {
      bundling: {
        image: lambda.Runtime.PYTHON_3_11.bundlingImage,
        command: [
          'bash',
          '-c',
          'pip install --no-cache-dir -r requirements.txt -t /asset-output && cp -r . /asset-output',
        ],
      },
    }),
    timeout: Duration.seconds(60),
    memorySize: 768,
    logGroup: toolLogGroup,
    environment: {
      STAGE: props.stageName,
      STATE_TABLE_NAME: stateTable.tableName,
      MODEL_ID: props.modelId,
      TICKER_UNIVERSE: 'AAPL,MSFT,AMZN,NVDA,JPM,JNJ,XOM,V',
    },
  });

  stateTable.grantReadWriteData(toolFunction);

  new events.Rule(scope, 'MarketDataPipelineRule', {
    description: 'Refresh yfinance market data and create a model input/run after market close.',
    schedule: events.Schedule.cron({
      minute: '0',
      hour: '23',
      weekDay: 'MON-FRI',
    }),
    targets: [
      new targets.LambdaFunction(toolFunction, {
        event: events.RuleTargetInput.fromObject({
          source: 'financial-planning.market-data-pipeline',
          detailType: 'CreateMarketDataModelRun',
          detail: {
            source: 'yfinance-market-data',
            portfolio_id: 'demo-growth-income',
            risk_target: 'moderate',
            symbols: ['AAPL', 'MSFT', 'AMZN', 'NVDA', 'JPM', 'JNJ', 'XOM', 'V'],
            period: '1y',
          },
        }),
      }),
    ],
  });

  return {
    stateTable,
    toolFunction,
  };
}
