#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { FinancialPlanningBackendApplicationStage } from '../lib/application-stage';
import { STAGES } from '../lib/config';
import { DeploymentPipelineStack } from '../lib/deployment-pipeline-stack';
import { FinancialPlanningBackendStack } from '../lib/financial-planning-backend-stack';

const app = new cdk.App();

new DeploymentPipelineStack(app, 'FinancialPlanningBackendPipelineStack', {
  env: {
    account: process.env.PIPELINE_ACCOUNT_ID ?? process.env.CDK_DEFAULT_ACCOUNT ?? '111111111111',
    region: process.env.PIPELINE_REGION ?? process.env.CDK_DEFAULT_REGION ?? 'us-east-2',
  },
});

for (const stage of STAGES) {
  new FinancialPlanningBackendStack(app, `FinancialPlanningBackend-${stage.stackSuffix}Stack`, {
    env: {
      account: stage.account,
      region: stage.region,
    },
    stage,
  });
}

app.synth();
