###Non-productrion Code###

from aws_cdk import (
    aws_codebuild as _codebuild,
    aws_codecommit as _codecommit,
    aws_codepipeline as _codepipeline,
    aws_codepipeline_actions as _codepipeline_actions,
    aws_iam as _iam,
    aws_s3 as _s3,
    core as cdk
)

class PipelineStack(cdk.Stack):

    def __init__(self, scope: cdk.Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # The code that defines your stack goes 
        # global region will use the global_template

        global_region, global_template = self.load_global_data()
        inputs_outputs, region_details = self.load_data() 
        code_repository_name = self.load_repo()
    
        #local region code deploy bucket
        bucket_name = "ArtifactsBucket-" + global_region['region']
        artifact_bucket_primary = _s3.Bucket(self, bucket_name)
        artifact_buckets = {}
        artifact_buckets[global_region['region']] = artifact_bucket_primary
        global_bucket = artifact_bucket_primary.bucket_name
        
        #get handle to each of the already existing code buckets in other regions
        for region in region_details:
            if 'importedBucket' in region:
              artifact_buckets[region['region']] = _s3.Bucket.from_bucket_name(self, 'artifactsBucket' + region['camelCase'], region['importedBucket']);

        #import code repository
        code_repo = _codecommit.Repository.from_repository_name(self, 'AppRepository', code_repository_name)

        source_output = _codepipeline.Artifact();

        pipeline = _codepipeline.Pipeline(self, 'Pipeline', cross_region_replication_buckets = artifact_buckets)

        pipeline.add_stage(
          stage_name = 'Source',
          actions = [
            _codepipeline_actions.CodeCommitSourceAction(
              action_name = 'CodeCommit_Source',
              repository = code_repo,
              output = source_output,
            )
          ]
        )
    
        buildOutput = _codepipeline.Artifact()

        #build environment variables
        envVars = self.create_envvars(global_region, global_template, region_details, inputs_outputs, global_bucket)
        
        # Declare a new CodeBuild project
        buildProject = _codebuild.PipelineProject(self, 'Build',
          environment = { 'build_image': _codebuild.LinuxBuildImage.AMAZON_LINUX_2_3 },
          environment_variables = envVars,
          build_spec = self.create_buildspec(global_region, global_template, region_details, inputs_outputs)
        )

        #add rights to codebuild policy to get to imported buckets/objects
        policy_stmt = _iam.PolicyStatement(actions=['s3:GetBucket*', 's3:List*', 's3:DeleteObject*',
          's3:PutObject', 's3:Abort*', 's3:GetObject*'])
        for region in region_details:
          if 'importedBucket' in region:
            policy_stmt.add_resources('arn:aws:s3:::'+region['importedBucket'], 'arn:aws:s3:::'+region['importedBucket']+'/*' )

        buildProject.add_to_role_policy(statement=policy_stmt)

        #Add the build stage to our pipeline
        pipeline.add_stage(
          stage_name = 'Build',
          actions = [
            _codepipeline_actions.CodeBuildAction(
              action_name = 'Build',
              project = buildProject,
              input = source_output,
              outputs = [buildOutput],
            ),
          ])

        #add global template change set and deploy
        changeSetStage = pipeline.add_stage(
          stage_name = 'Create_Global_Change_Sets_{}'.format(global_region['region'])
        )
        deployStage = pipeline.add_stage(
          stage_name = 'Deploy_Global_Stacks_{}'.format(global_region['region'])
        )
        changeSetStage.add_action(_codepipeline_actions.CloudFormationCreateReplaceChangeSetAction(
          action_name =  '{}-Create-Change-Set-{}'.format(global_region['region'], global_template['templateName']),
          template_path = buildOutput.at_path(self.create_output_template(global_template, global_region)),
          stack_name = global_template['stackName'],
          admin_permissions = True,
          region = global_region['region'],
          change_set_name = global_template['stackName'] +'-changeset',
          run_order = 1
        ));
        deployStage.add_action(_codepipeline_actions.CloudFormationExecuteChangeSetAction(
          action_name = '{}-Deploy-{}'.format(global_region['region'], global_template['templateName']),
          stack_name = global_template['stackName'],
          change_set_name =  '{}-changeset'.format(global_template['stackName']),
          region = global_region['region'],
          run_order = 1
        ))

        #by region, add createchangeset and executechangeset for each template 
        for region in region_details:
          changeSetStage = pipeline.add_stage(
            stage_name = 'Create_Change_Sets_{}'.format(region['region'])
          )
          deployStage = pipeline.add_stage(
            stage_name = 'Deploy_Stacks_{}'.format(region['region'])
          )
          for count, _input in enumerate(inputs_outputs):
            changeSetStage.add_action(_codepipeline_actions.CloudFormationCreateReplaceChangeSetAction(
                action_name =  '{}-Create-Change-Set-{}'.format(region['region'], _input['templateName']),
                template_path = buildOutput.at_path(self.create_output_template(_input, region)),
                stack_name = _input['stackName'],
                admin_permissions = True,
                region = region['region'],
                change_set_name = _input['stackName'] +'-changeset',
                run_order = count+1
              ));
            deployStage.add_action(_codepipeline_actions.CloudFormationExecuteChangeSetAction(
              action_name = '{}-Deploy-{}'.format(region['region'], _input['templateName']),
              stack_name = _input['stackName'],
              change_set_name =  '{}-changeset'.format(_input['stackName']),
              region = region['region'],
              run_order = count+1
            ))
            
    def remove_dash(self, str_remove):
      #fixer for environment varialbes to remove - characters
      return str_remove.replace('-', '_')
      
    def create_output_template(self, input_template, region):
      #standard formatting for output template names
      template_output_postfix = '-output'
      template_extension = '.yaml'
      return '{}{}-{}{}'.format(input_template['templateName'], template_output_postfix, 
        region['region'].upper(), template_extension)

    def create_output_template_var(self, template, region):
      #standard formatting for output template enviornment variable
      return self.remove_dash('OUTPUT_TEMPLATE_{}_{}'.format(template['templateName'].upper(), region['region'].upper()))

    def create_output_bucket_var(self, region):
      #standard formatting for output bucket ennvironment variable
      return self.remove_dash('PACKAGE_BUCKET_{}'.format(region['region'].upper()))

    def create_buildspec(self, global_region, global_template, regions, inputs_outputs):
      #generate the buildspec from the templates and regions
      file_extension = '.yaml'
      buildspec = {}
      buildspec['version'] = '0.2'
      install = { 
        'on-failure' : 'ABORT',
        'runtime-versions' :  {'dotnet': 3.1},
        'commands' : [
          'pip3 install --upgrade aws-sam-cli==1.23.0',
          'dotnet tool install --global Amazon.Lambda.Tools --version 5.1.1'
        ]
      }

      pre_build = {
        'on-failure': 'ABORT',
        'commands' : [
          'dotnet lambda help',
          'sam --version'
          ]
      }

      commands = []
      files = []
      #process global template first and then loop through stacks
      commands.append('sam build --template-file {}{}'.
        format(global_template['templateName'], file_extension))
      output_var = self.create_output_template_var(global_template, global_region)
      commands.append(
        'sam package --s3-bucket ${} --output-template-file ${} --region {}'
        .format(self.create_output_bucket_var(global_region),
        output_var,
        global_region['region']))
      files.append('${}'.format(output_var))
      
      for _input in inputs_outputs:
        commands.append('sam build --template-file {}{}'.
          format(_input['templateName'], file_extension))
        for region in regions:
          output_var = self.create_output_template_var(_input, region)
          commands.append(
            'sam package --s3-bucket ${} --output-template-file ${} --region {}'
            .format(self.create_output_bucket_var(region),
            output_var,
            region['region']))
          files.append('${}'.format(output_var))
      build = {
        'on-failure': 'ABORT',
        'commands': commands
      }

      post_build = {
        'on-failure': 'ABORT',
        'commands' : []
      }
      buildspec['phases'] = { 'install': install, 'pre_build': pre_build, 
        'build': build, 'post_build': post_build }

      artifacts = {
        'files': files,
        'discard-paths': 'yes'
      }
      buildspec['artifacts'] = artifacts
      
      build_spec = _codebuild.BuildSpec.from_object_to_yaml(buildspec)
      return build_spec

    def create_envvars(self, global_region, global_template, region_details, inputs_outputs, global_bucket):
      #build the environment variables needed to support sam package commands      
      #envvars can be deleted since the buildspec is also generated.  they are left here
      #until changes for buildspec generation are complete
      envVars = {}
      envVar = self.create_output_template_var(global_template, global_region)
      var = self.create_output_template(global_template, global_region)
      envVars[envVar] = _codebuild.BuildEnvironmentVariable(value=var)
      for region in region_details:
        envVar = self.create_output_bucket_var(region)
        #PACKAGE_BUCKET_REGION vars
        if 'importedBucket' in region:
          envVars[envVar] = _codebuild.BuildEnvironmentVariable(value=region['importedBucket'])
        else:
          envVars[envVar] = _codebuild.BuildEnvironmentVariable(value=global_bucket)
        for _input in inputs_outputs:
          #OUTPUT_TEMPLATE_REGION vars
          envVar = self.create_output_template_var(_input, region)
          var = self.create_output_template(_input, region)
          envVars[envVar] = _codebuild.BuildEnvironmentVariable(value=var)
      return envVars

    def load_global_data(self):
      global_region = {'region' : 'us-east-1'}
      global_template = {'templateName': 'global_template', 'stackName': 'global-stack' }
      return global_region, global_template
    
    #define regions and templates for the pipeline
    def load_data(self):
      #mappings for templates to stack names
      #enter the template name, without the extensions and the stack name that you wish to deploy to
      inputs_outputs = [{ 'templateName': 'template1', 'stackName' : 'samdotnet-test1'},
        {'templateName': 'template2', 'stackName' : 'samdotnet-test2'},
        {'templateName': 'template3', 'stackName' : 'samdotnet-test3'}]
      #region order matters for the pipeline - camelCase may be used in future versions
      #use regions you wish to use following the formats below
      region_details = [
          {'region' : 'us-east-1', 'camelCase' : 'UsEast1' },  #main/global region will have a bucket created in it
          {'region' : 'us-east-2', 'importedBucket' : '[bucket in us-east-2]', 'camelCase' : 'UsEast2' },
          {'region' : 'us-west-1', 'importedBucket' : '[bucket in us-west-1]', 'camelCase' : 'UsWest1' }, 
          {'region' : 'us-west-2', 'importedBucket' : '[bucket in us-west-2]', 'camelCase' : 'UsWest2' },
          {'region' : 'eu-west-1', 'importedBucket' : '[bucket in eu-west-1]', 'camelCase' : 'EuWest1' },
          {'region' : 'eu-west-2', 'importedBucket' : '[bucket in eu-west-2]', 'camelCase' : 'EuWest2' }
      ]
      return inputs_outputs, region_details

    def load_repo(self):
      return 'yourrepogoeshere'