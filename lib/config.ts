export interface StageConfig {
  readonly name: 'personal' | 'alpha' | 'gamma' | 'prod';
  readonly stackSuffix: 'Personal' | 'Alpha' | 'Gamma' | 'Prod';
  readonly account: string;
  readonly region: string;
  readonly removalPolicy: 'destroy' | 'retain';
  readonly runtimeName: string;
}

const defaultAccount = process.env.CDK_DEFAULT_ACCOUNT ?? '111111111111';
const defaultRegion = process.env.AGENTCORE_REGION ?? 'us-west-2';

export const STAGES: StageConfig[] = [
  {
    name: 'personal',
    stackSuffix: 'Personal',
    account: process.env.PERSONAL_ACCOUNT_ID ?? defaultAccount,
    region: process.env.PERSONAL_REGION ?? defaultRegion,
    removalPolicy: 'destroy',
    runtimeName: 'financial_planning_personal',
  },
  {
    name: 'alpha',
    stackSuffix: 'Alpha',
    account: process.env.ALPHA_ACCOUNT_ID ?? defaultAccount,
    region: process.env.ALPHA_REGION ?? defaultRegion,
    removalPolicy: 'retain',
    runtimeName: 'financial_planning_alpha',
  },
  {
    name: 'gamma',
    stackSuffix: 'Gamma',
    account: process.env.GAMMA_ACCOUNT_ID ?? defaultAccount,
    region: process.env.GAMMA_REGION ?? defaultRegion,
    removalPolicy: 'retain',
    runtimeName: 'financial_planning_gamma',
  },
  {
    name: 'prod',
    stackSuffix: 'Prod',
    account: process.env.PROD_ACCOUNT_ID ?? defaultAccount,
    region: process.env.PROD_REGION ?? defaultRegion,
    removalPolicy: 'retain',
    runtimeName: 'financial_planning_prod',
  },
];

export const DEFAULT_MODEL_ID =
  process.env.AGENT_MODEL_ID ?? 'us.amazon.nova-2-lite-v1:0';

export const DEFAULT_JUDGE_MODEL_ID =
  process.env.EVAL_JUDGE_MODEL_ID ?? 'us.amazon.nova-2-lite-v1:0';
