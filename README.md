
# CDK Mono-repo, multi-project, multi-region CodePipeline

This project creates a custom CI/CD CodePipeline using variables for your project. You simply fill in details about the templates, stacks, regions, and buckets and the CDK will generate the pipeline.

### Installation Information and Guide

This project was built and tested with CDK 1.110.1 and Python 3.7.10.

1. [Install CDK](https://docs.aws.amazon.com/cdk/latest/guide/getting_started.html)
2. [Install Python 3.7.10](https://www.python.org/downloads/release/python-3710/)
3. Clone this repo
4. Create a virtualenv in Python `python3 -m venv .venv` in the project directory
5. Activate your virtualenv `. .venv/bin/activate`
6. Install python requirements using `pip install -r requirements.txt`
7. Create a CloudFormation template using `cdk synth`
8. Deploy the stack using `cdk deploy`

### Assumption
The global region is assumed to be the region that you run and deploy this stack to. It has not been tested with a deployment from another region.

### Customizations

1. Define your regions and buckets in load_data

Region data follows the format of {region: 'region-with-dashes', importedBucket: 'bucket name in region', camelCase: 'camelCaseOfRegion'}.  This is set in the 'region_details' variable.

The global region will have a bucket created as part of the pipeline and does not need an importedBucket.

2. Define your templates and stacks in load_data

Templates and stacks follow the format of {templateName: 'template-with-no-extension', stackName: 'name-of-stack-to-deploy'}. This is set in inputs_outputs

3. Define your global region and global template.

The global region and global template are special cases. The global template will only be packaged and deployed to the global region that is identified.

Global region is defined in load_global_data and follows the format of {region: 'region-with-dashes', camelCase: 'camelCaseOfRegion'} and the global template follows the format of {templateName: 'global-template-no-extension', stackName: 'stack-to-deploy-to'}

4. Define your Repository

The repository to pull code from is defined in load_repo. It is assumed to be a CodeCommit repository for this project.