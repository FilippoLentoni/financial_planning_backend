import { Stage, StageProps } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import { FinancialPlanningBackendStack } from './financial-planning-backend-stack';
import { StageConfig } from './config';

export interface FinancialPlanningBackendApplicationStageProps extends StageProps {
  readonly stageConfig: StageConfig;
}

export class FinancialPlanningBackendApplicationStage extends Stage {
  constructor(scope: Construct, id: string, props: FinancialPlanningBackendApplicationStageProps) {
    super(scope, id, props);

    new FinancialPlanningBackendStack(this, 'Application', {
      env: {
        account: props.stageConfig.account,
        region: props.stageConfig.region,
      },
      stackName: `FinancialPlanningBackend-${props.stageConfig.stackSuffix}Stack`,
      stage: props.stageConfig,
    });
  }
}
