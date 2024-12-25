#!/bin/bash

# Step 1: Run the Python script
echo "Running model modification patch..."
python model_modification_patch.py

# Step 2: Switch env files and build
cd ../../web-app/

if [ -f .env ]; then
    echo "Backing up .env to .env.bak..."
    mv .env .env.bak
fi

if [ -f .env.generated ]; then
    echo "Renaming .env.generated to .env..."
    cp .env.generated .env
else
    echo "Warning: .env.generated not found!"
    exit 1
fi

echo "Running npm build..."
npm run build

# Step 3: Restore original .env
if [ -f .env.bak ]; then
    echo "Restoring original .env..."
    mv .env.bak .env
fi

# Step 4: Upload to S3
echo "Getting S3 bucket name from CloudFormation..."
S3_BUCKET=$(aws cloudformation describe-stacks \
    --stack-name MultiModalVideoAnalyticsWebAppStack \
    --query 'Stacks[0].Outputs[?OutputKey==`webappbucket`].OutputValue' \
    --output text)

if [ -z "$S3_BUCKET" ]; then
    echo "Error: Could not get S3 bucket name from CloudFormation"
    exit 1
fi

echo "Emptying S3 bucket ${S3_BUCKET}..."
aws s3 rm s3://${S3_BUCKET} --recursive

echo "Uploading new content to S3..."
aws s3 sync dist/ s3://${S3_BUCKET}
aws s3 cp .env.generated s3://${S3_BUCKET}/.env

echo "Done!"