import {
  Stack,
  StackProps,
  aws_codebuild as codebuild,
  aws_codepipeline as codepipeline,
  pipelines,
} from 'aws-cdk-lib';
import { Construct } from 'constructs';
import { FinancialPlanningBackendApplicationStage } from './application-stage';
import { STAGES } from './config';

const sourceRepo = process.env.SOURCE_REPO ?? 'FilippoLentoni/financial_planning';
const sourceBranch = process.env.SOURCE_BRANCH ?? 'main';
const sourceConnectionArn =
  process.env.CODESTAR_CONNECTION_ARN ??
  'arn:aws:codeconnections:us-east-2:111111111111:connection/replace-me';

export class DeploymentPipelineStack extends Stack {
  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);

    const pipeline = new pipelines.CodePipeline(this, 'Pipeline', {
      pipelineName: 'FinancialPlanningBackendDeploymentPipeline',
      pipelineType: codepipeline.PipelineType.V2,
      crossAccountKeys: true,
      dockerEnabledForSynth: true,
      dockerEnabledForSelfMutation: true,
      assetPublishingCodeBuildDefaults: {
        buildEnvironment: {
          buildImage: codebuild.LinuxArmBuildImage.AMAZON_LINUX_2_STANDARD_3_0,
          computeType: codebuild.ComputeType.SMALL,
          privileged: true,
        },
      },
      synth: new pipelines.ShellStep('Synth', {
        input: pipelines.CodePipelineSource.connection(sourceRepo, sourceBranch, {
          connectionArn: sourceConnectionArn,
        }),
        env: {
          SOURCE_REPO: sourceRepo,
          SOURCE_BRANCH: sourceBranch,
          CODESTAR_CONNECTION_ARN: sourceConnectionArn,
          CDK_DEFAULT_ACCOUNT: Stack.of(this).account,
          CDK_DEFAULT_REGION: Stack.of(this).region,
        },
        commands: [
          'npm ci',
          'python3 -m pip install -r evaluator/requirements.txt',
          'npm test',
          'npm run synth',
        ],
      }),
    });

    for (const stageConfig of STAGES.filter((stage) => stage.name !== 'personal')) {
      const appStage = new FinancialPlanningBackendApplicationStage(this, stageConfig.stackSuffix, {
        env: {
          account: stageConfig.account,
          region: stageConfig.region,
        },
        stageConfig,
      });

      const requiresApproval = stageConfig.name === 'gamma' || stageConfig.name === 'prod';
      pipeline.addStage(appStage, {
        pre: requiresApproval
          ? [new pipelines.ManualApprovalStep(`Approve-${stageConfig.stackSuffix}`)]
          : undefined,
      });
    }
  }
}
