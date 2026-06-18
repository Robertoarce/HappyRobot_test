import { makeClient, getApiKey } from "./client.js";

/** Verifies the platform API key by introspecting it. */
async function main() {
  const key = getApiKey();
  const masked = key.length > 10 ? `${key.slice(0, 7)}...${key.slice(-4)}` : "(short)";
  console.log(`Checking HappyRobot API key ${masked} ...`);

  const client = makeClient();
  try {
    const info = await client.apiKey.describe();
    console.log("AUTH OK. Key info:");
    console.log(JSON.stringify(info, null, 2));
  } catch (err: any) {
    console.error("AUTH FAILED:", err?.status ?? "", err?.message ?? err);
    if (err?.response) {
      try {
        console.error("Body:", JSON.stringify(await err.response.json?.(), null, 2));
      } catch {
        /* ignore */
      }
    }
    process.exitCode = 1;
  }
}

main();
