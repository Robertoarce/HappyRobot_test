import "dotenv/config";
import { HappyRobotClient } from "@happyrobot-ai/sdk";

export function getApiKey(): string {
  const key = process.env.HAPPYROBOT_API_KEY;
  if (!key) {
    throw new Error(
      "HAPPYROBOT_API_KEY is not set. Add it to platform/.env " +
        "(generate at Settings -> API Keys on the HappyRobot platform).",
    );
  }
  return key;
}

export function makeClient(): HappyRobotClient {
  const cluster = (process.env.HAPPYROBOT_CLUSTER as "us" | "eu") ?? "us";
  return new HappyRobotClient({
    apiKey: getApiKey(),
    cluster,
    maxRetries: 2,
  });
}
