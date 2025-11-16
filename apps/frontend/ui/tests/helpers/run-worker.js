import { Worker } from "node:worker_threads";

export const runWorker = (url) =>
  new Promise((resolve, reject) => {
    const worker = new Worker(url, { type: "module" });
    worker.once("message", resolve);
    worker.once("error", reject);
    worker.once("exit", (code) => {
      if (code !== 0) {
        reject(new Error(`Worker exited with code ${code}`));
      }
    });
  });
