import boto3
import json
from datetime import datetime, timedelta
import time


def lambda_handler(event, context):
    client = boto3.client('logs')
    sns_client = boto3.client('sns')

    query = "fields @timestamp, @message | filter @message like /Time taken to perform_chat:/ | sort @timestamp desc | limit 10000"

    log_group = 'jprochat'

    start_query_response = client.start_query(
        logGroupName=log_group,
        startTime=int((datetime.today() - timedelta(hours=24)).timestamp()),
        endTime=int(datetime.now().timestamp()),
        queryString=query,
    )

    query_id = start_query_response['queryId']

    response = None

    while response == None or response['status'] == 'Running':
        print('Waiting for query to complete ...')
        time.sleep(1)
        response = client.get_query_results(
            queryId=query_id
        )

    results = response['results']

    loglines = []
    lastmsg = ""
    for result in results:
        msg = result[1]['value']
        if msg == lastmsg:
            continue

        loglines.append(msg)
        lastmsg = msg

    if len(loglines) <= 0:
        loglines.append(u"Ingen spørsmål i dag")

    today = (datetime.today() - timedelta(hours=1)).strftime('%d-%m-%Y')

    response = sns_client.publish(
        TopicArn="arn:aws:sns:eu-west-1:211125634171:jprochat",
        Message=json.dumps({'default': json.dumps(loglines, indent=2, ensure_ascii=False)}),
        MessageStructure='json',
        Subject=f"jprochat questions {today}"
    )

    print(f"Got sns response {response}")

    return {
        'statusCode': 200,
        'body': response
    }
