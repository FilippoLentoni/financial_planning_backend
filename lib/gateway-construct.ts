import * as path from 'path';
import {
  Duration,
  RemovalPolicy,
  aws_apigateway as apigateway,
  aws_iam as iam,
  aws_lambda as lambda,
  aws_logs as logs,
} from 'aws-cdk-lib';
import {
  Gateway,
  GatewayAuthorizer,
  GatewayExceptionLevel,
  GatewayProtocol,
  MCPProtocolVersion,
  McpGatewaySearchType,
  SchemaDefinitionType,
  ToolDefinition,
  ToolSchema,
} from '@aws-cdk/aws-bedrock-agentcore-alpha';
import { Construct } from 'constructs';

export interface GatewayResourcesProps {
  readonly api: apigateway.RestApi;
  readonly toolFunction: lambda.Function;
  readonly stageName: string;
  readonly runtimeRole: iam.IRole;
  readonly removalPolicy: RemovalPolicy;
}

export interface GatewayResources {
  readonly agentCoreGateway: Gateway;
  readonly gatewayProxyFunction: lambda.Function;
  readonly gatewaysUrl: string;
  readonly mcpProxyUrl: string;
  readonly agentCoreGatewayUrl: string;
  readonly agentCoreGatewayArn: string;
}

export function createGatewayResources(
  scope: Construct,
  props: GatewayResourcesProps,
): GatewayResources {
  const agentCoreGateway = new Gateway(scope, 'PortfolioPlanningGateway', {
    gatewayName: `financial-planning-${props.stageName}`,
    description: 'MCP gateway for financial planning portfolio optimization tools.',
    authorizerConfiguration: GatewayAuthorizer.usingAwsIam(),
    exceptionLevel: GatewayExceptionLevel.DEBUG,
    protocolConfiguration: GatewayProtocol.mcp({
      supportedVersions: [MCPProtocolVersion.MCP_2025_06_18, MCPProtocolVersion.MCP_2025_03_26],
      searchType: McpGatewaySearchType.SEMANTIC,
      instructions:
        'Use these tools to inspect synthetic portfolios, run 16-week portfolio optimization, retrieve simulations, perform what-if analysis, and generate weekly planning reports.',
    }),
    tags: {
      app: 'financial-planning-backend',
      stage: props.stageName,
    },
  });

  agentCoreGateway.addLambdaTarget('PortfolioPlanningToolsTarget', {
    gatewayTargetName: 'portfolio-planning',
    description: 'Portfolio planning tools implemented by a Lambda target.',
    lambdaFunction: props.toolFunction,
    toolSchema: ToolSchema.fromInline(PORTFOLIO_PLANNING_TOOL_SCHEMA),
  });
  agentCoreGateway.grantInvoke(props.runtimeRole);

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
    agentCoreGateway,
    gatewayProxyFunction,
    gatewaysUrl: `${props.api.url}gateways/iam`,
    mcpProxyUrl: `${props.api.url}mcp/proxy`,
    agentCoreGatewayUrl: agentCoreGateway.gatewayUrl ?? '',
    agentCoreGatewayArn: agentCoreGateway.gatewayArn,
  };
}

const stringArraySchema = {
  type: SchemaDefinitionType.ARRAY,
  items: { type: SchemaDefinitionType.STRING },
};

const PORTFOLIO_PLANNING_TOOL_SCHEMA: ToolDefinition[] = [
  {
    name: 'list-portfolios',
    description: 'List synthetic portfolios available for planning.',
    inputSchema: { type: SchemaDefinitionType.OBJECT, properties: {}, required: [] },
  },
  {
    name: 'get-portfolio-snapshot',
    description: 'Return current synthetic holdings, cash, prices, and portfolio value.',
    inputSchema: {
      type: SchemaDefinitionType.OBJECT,
      properties: {
        portfolio_id: {
          type: SchemaDefinitionType.STRING,
          description: 'Portfolio identifier. Defaults to demo-growth-income.',
        },
        cash: {
          type: SchemaDefinitionType.NUMBER,
          description: 'Optional cash amount to include in the snapshot.',
        },
      },
      required: [],
    },
  },
  {
    name: 'get-market-context',
    description: 'Return synthetic daily market and news context for tracked stocks.',
    inputSchema: {
      type: SchemaDefinitionType.OBJECT,
      properties: {
        symbols: {
          ...stringArraySchema,
          description: 'Optional list of stock symbols.',
        },
      },
      required: [],
    },
  },
  {
    name: 'run-portfolio-optimization',
    description: 'Create a cost-safe 16-week synthetic buy/sell optimization plan.',
    inputSchema: {
      type: SchemaDefinitionType.OBJECT,
      properties: {
        portfolio_id: { type: SchemaDefinitionType.STRING },
        risk_target: {
          type: SchemaDefinitionType.STRING,
          description: 'One of conservative, moderate, or growth.',
        },
        cash_available: { type: SchemaDefinitionType.NUMBER },
        max_trade_value_per_week: { type: SchemaDefinitionType.NUMBER },
      },
      required: [],
    },
  },
  {
    name: 'get-simulation-status',
    description: 'Read synthetic optimization simulation status.',
    inputSchema: {
      type: SchemaDefinitionType.OBJECT,
      properties: {
        simulation_id: { type: SchemaDefinitionType.STRING },
      },
      required: ['simulation_id'],
    },
  },
  {
    name: 'get-simulation-results',
    description: 'Retrieve the generated 16-week trade plan and expected portfolio path.',
    inputSchema: {
      type: SchemaDefinitionType.OBJECT,
      properties: {
        simulation_id: { type: SchemaDefinitionType.STRING },
      },
      required: ['simulation_id'],
    },
  },
  {
    name: 'run-what-if-analysis',
    description: 'Analyze liquidity, adherence, or forecast-shock impact on a 16-week plan.',
    inputSchema: {
      type: SchemaDefinitionType.OBJECT,
      properties: {
        simulation_id: { type: SchemaDefinitionType.STRING },
        cash_available: { type: SchemaDefinitionType.NUMBER },
        forecast_shock_pct: { type: SchemaDefinitionType.NUMBER },
        missed_trade_symbols: stringArraySchema,
      },
      required: ['simulation_id'],
    },
  },
  {
    name: 'explain-trade-plan',
    description: 'Explain why the dummy optimizer suggests each buy/sell action.',
    inputSchema: {
      type: SchemaDefinitionType.OBJECT,
      properties: {
        simulation_id: { type: SchemaDefinitionType.STRING },
      },
      required: ['simulation_id'],
    },
  },
  {
    name: 'record-weekly-review',
    description: 'Record a weekly review snapshot and adherence notes for the current plan.',
    inputSchema: {
      type: SchemaDefinitionType.OBJECT,
      properties: {
        simulation_id: { type: SchemaDefinitionType.STRING },
        week: { type: SchemaDefinitionType.INTEGER },
        actual_cash: { type: SchemaDefinitionType.NUMBER },
        actual_value: { type: SchemaDefinitionType.NUMBER },
        notes: { type: SchemaDefinitionType.STRING },
      },
      required: ['simulation_id', 'week'],
    },
  },
  {
    name: 'generate-weekly-plan-report',
    description: 'Generate a weekly report summarizing the next 16 weeks and deviations from the prior plan.',
    inputSchema: {
      type: SchemaDefinitionType.OBJECT,
      properties: {
        simulation_id: { type: SchemaDefinitionType.STRING },
        previous_simulation_id: { type: SchemaDefinitionType.STRING },
        week: { type: SchemaDefinitionType.INTEGER },
      },
      required: ['simulation_id'],
    },
  },
  {
    name: 'get_model_input',
    description: 'Return the model input payload used for a portfolio optimization run.',
    inputSchema: {
      type: SchemaDefinitionType.OBJECT,
      properties: {
        run_id: { type: SchemaDefinitionType.STRING },
      },
      required: ['run_id'],
    },
  },
  {
    name: 'get_model_output',
    description: 'Return the model output payload generated by a portfolio optimization run.',
    inputSchema: {
      type: SchemaDefinitionType.OBJECT,
      properties: {
        run_id: { type: SchemaDefinitionType.STRING },
      },
      required: ['run_id'],
    },
  },
  {
    name: 'override_input',
    description: 'Create a new model input by applying synthetic overrides to an existing input.',
    inputSchema: {
      type: SchemaDefinitionType.OBJECT,
      properties: {
        input_id: { type: SchemaDefinitionType.STRING },
        overrides: { type: SchemaDefinitionType.OBJECT },
        justification: { type: SchemaDefinitionType.STRING },
      },
      required: ['input_id'],
    },
  },
  {
    name: 'get_model_formulation',
    description: 'Return the synthetic math-model formulation for a portfolio optimization run.',
    inputSchema: {
      type: SchemaDefinitionType.OBJECT,
      properties: {
        run_id: { type: SchemaDefinitionType.STRING },
      },
      required: ['run_id'],
    },
  },
  {
    name: 'run_math_model',
    description: 'Run the synthetic portfolio optimization math model for a stored input payload.',
    inputSchema: {
      type: SchemaDefinitionType.OBJECT,
      properties: {
        input_id: { type: SchemaDefinitionType.STRING },
      },
      required: ['input_id'],
    },
  },
  {
    name: 'override',
    description: 'Record a governed manual override decision for a model input.',
    inputSchema: {
      type: SchemaDefinitionType.OBJECT,
      properties: {
        input_id: { type: SchemaDefinitionType.STRING },
        justification: { type: SchemaDefinitionType.STRING },
      },
      required: ['input_id', 'justification'],
    },
  },
];
