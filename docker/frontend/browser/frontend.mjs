import { execFileSync, spawnSync } from "node:child_process";

const IMAGE = process.env.CIPHERMOTH_FRONTEND_IMAGE ?? "ciphermoth-frontend:browser-test";

export const startFrontend = async (apiUrl) => {
  const name = `ciphermoth-browser-${process.pid}-${Math.random().toString(36).slice(2, 8)}`;
  execFileSync("docker", [
    "run",
    "-d",
    "--rm",
    "--name",
    name,
    "-e",
    `VITE_API_URL=${apiUrl}`,
    "-p",
    "127.0.0.1::3000",
    IMAGE,
  ]);
  const port = execFileSync("docker", ["port", name, "3000/tcp"])
    .toString()
    .trim()
    .split(":")
    .pop();
  const url = `http://127.0.0.1:${port}`;
  for (let attempt = 0; attempt < 100; attempt += 1) {
    try {
      if ((await fetch(url)).ok) return { name, url };
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 200));
    }
  }
  const logs = execFileSync("docker", ["logs", name]).toString();
  spawnSync("docker", ["rm", "-f", name]);
  throw new Error(`frontend did not start:\n${logs}`);
};

export const stopFrontend = (frontend) => {
  if (frontend) spawnSync("docker", ["rm", "-f", frontend.name]);
};
