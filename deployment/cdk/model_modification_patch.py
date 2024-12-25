import boto3
import json
import os

# all cloudformation outputs
# region_name = os.environ.get('AWS_DEFAULT_REGION')
cloudformation = boto3.client('cloudformation')
stack_name = 'MultiModalVideoAnalyticsWebAppStack'
response = cloudformation.describe_stacks(StackName=stack_name)
outputs = response['Stacks'][0]['Outputs']

lambda_names = []
lambda_keys = ['analysislambda', 'summarylambda', 'vqalambda', 'agentlambda', 'retrievelambda']
print("\nGathering Lambda function names...")
for key in lambda_keys:
    lambda_name = [output['OutputValue'] for output in outputs if output['OutputKey'] == key][0]
    lambda_names.append(lambda_name)
    print(f"Found {key}: {lambda_name}")

# Update lambda environment variables
lambda_client = boto3.client('lambda')

print("\nReading model configuration...")
with open('model_config.json', 'r') as config_file:
    model_config = json.load(config_file)
brc_enable = 'Y' if model_config.get('brconnector_enable', '') == 'true' else 'N'
vqa_model = model_config.get('vqa_model', '')
postprocess_model = model_config.get('postprocess_mode', '')
opensearch_preprocess_model = model_config.get('opensearch_preprocess_model', '')        

for lambda_name in lambda_names:
    # Get current configuration
    current_config = lambda_client.get_function_configuration(FunctionName=lambda_name)
    current_env = current_config.get('Environment', {}).get('Variables', {})
    
    # Update only BRC_ENABLE while preserving other variables
    current_env['BRC_ENABLE'] = brc_enable
    
    # Update lambda configuration
    lambda_client.update_function_configuration(
        FunctionName=lambda_name,
        Environment={
            'Variables': current_env
        }
    )

# Get and update configuration for VQA lambda
current_config = lambda_client.get_function_configuration(FunctionName=lambda_names[2])
current_env = current_config.get('Environment', {}).get('Variables', {})
current_env['MODEL_NAME'] = vqa_model
lambda_client.update_function_configuration(
    FunctionName=lambda_names[2],
    Environment={
        'Variables': current_env
    }
)

# Get and update configuration for postprocess lambda
current_config = lambda_client.get_function_configuration(FunctionName=lambda_names[3])
current_env = current_config.get('Environment', {}).get('Variables', {})
current_env['MODEL_NAME'] = postprocess_model
lambda_client.update_function_configuration(
    FunctionName=lambda_names[3],
    Environment={
        'Variables': current_env
    }
)

# Get and update configuration for opensearch preprocess lambda
current_config = lambda_client.get_function_configuration(FunctionName=lambda_names[4])
current_env = current_config.get('Environment', {}).get('Variables', {})
current_env['MODEL_NAME'] = opensearch_preprocess_model
lambda_client.update_function_configuration(
    FunctionName=lambda_names[4],
    Environment={
        'Variables': current_env
    }
)
print(f"Updated all environment variables")
    
webapp_bucket = [output['OutputValue'] for output in outputs if output['OutputKey'] == 'webappbucket'][0]

# Download .env file from S3
s3_client = boto3.client('s3')
output_dir = '../../web-app'
output_file = output_dir + '/.env.generated'

# Create directory if it doesn't exist
try:
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
except OSError as e:
    print(f"Error creating directory: {str(e)}")

try:
    s3_client.download_file(webapp_bucket, '.env', output_file)
    print(f"Successfully downloaded .env file to {output_file}")
except Exception as e:
    print(f"Error downloading .env file: {str(e)}")