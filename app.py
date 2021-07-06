#!/usr/bin/env python3

###Non production code###

import os

from aws_cdk import core as cdk

from aws_cdk import core

from pipeline.pipeline_stack import PipelineStack


app = core.App()
#region and account are needed for cross-region deployment
env = { 'account': os.environ.get('CDK_DEFAULT_ACCOUNT'), 'region': os.environ.get('CDK_DEFAULT_REGION') }
PipelineStack(app, "PipelineStack", env=env)

app.synth()
