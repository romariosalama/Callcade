# AWS setup

Callcade runs fine in demo mode with no AWS account. These steps turn on the real AI buyers (Amazon Bedrock) and the realistic voices (Amazon Polly). It takes about 30 minutes.

AWS moves things around in the console sometimes. If a button isn't where this says, use the search bar at the top of the console.

**Cost:** Bedrock and Polly charge per use. A 10-turn practice call is a few cents at most. Check the current prices on the [Bedrock](https://aws.amazon.com/bedrock/pricing/) and [Polly](https://aws.amazon.com/polly/pricing/) pricing pages, and do step 2 so nothing surprises you.

## 1. Secure the root account

Sign in to the [AWS console](https://console.aws.amazon.com/), click your account name (top right), go to **Security credentials**, and set up **MFA** with an authenticator app.

## 2. Set a budget alert

Search **Budgets** → **Create budget** → **Use a template** → **Monthly cost budget**. Set it to **$5** and add your email. AWS will email you if spending gets close.

## 3. Turn on the Claude model in Bedrock

1. Switch the region (top right) to **US East (N. Virginia) us-east-1**.
2. Open **Amazon Bedrock** → **Model catalog** → **Claude Haiku 4.5**.
3. Open it in the **Playground** and send "hi". The first time you use an Anthropic model, AWS may ask you to fill out a short use case form ("personal portfolio project, a sales training game" is fine).
4. If you get a reply, it's ready.

## 4. Create a user that can only do what the app needs

1. **IAM** → **Users** → **Create user**. Name it `callcade-dev`, no console access.
2. **Attach policies directly** → **Create policy** → **JSON**, and paste:

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream", "polly:SynthesizeSpeech"],
         "Resource": "*"
       }
     ]
   }
   ```

   Name it `CallcadeAppAccess`, create it, then attach it to the user.
3. Open the user → **Security credentials** → **Create access key** → **Local code**. Copy both keys (the secret only shows once).

This user can call the AI and make voices, and nothing else, so even a leaked key can't spin up servers. Never put the keys in the code, `.env`, a screenshot, or GitHub.

## 5. Give your computer the keys

Install the AWS CLI (`brew install awscli`, or the installer from [aws.amazon.com/cli](https://aws.amazon.com/cli/)), then run:

```bash
aws configure
```

Paste the two keys, region `us-east-1`, output `json`. The keys get saved in `~/.aws/credentials`, outside the project.

Test it:

```bash
aws bedrock-runtime converse \
  --model-id us.anthropic.claude-haiku-4-5-20251001-v1:0 \
  --messages '[{"role":"user","content":[{"text":"Say hi in five words."}]}]'

aws polly synthesize-speech --voice-id Matthew --engine neural --output-format mp3 \
  --text "Hi, who is this?" test.mp3
```

## 6. Turn it on

In `.env`:

```
CALLCADE_MODE=bedrock
CALLCADE_VOICE=polly
```

Restart the server. The badge in the top right should say **AI buyers on**.

## Troubleshooting

| Error has | Meaning | Fix |
| --- | --- | --- |
| `AccessDeniedException` ... model | Model not enabled yet, or the form is pending | Redo step 3 and wait |
| `not authorized to perform` | The user is missing the policy | Redo step 4 |
| `model identifier is invalid` | Wrong model ID for your region | Bedrock console → **Cross-region inference**, copy the Claude Haiku 4.5 ID into `BEDROCK_MODEL_ID` |
| `Unable to locate credentials` | `aws configure` wasn't run | Redo step 5 |
| `ThrottlingException` | Too many requests | Wait a few seconds |

If a voice sounds off or doesn't work, the app automatically tries Polly's generative, then neural, then standard engine, and falls back to the browser voice if Polly fails.
