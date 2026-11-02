import { boundedJson } from "./response.ts";
export interface GenerationParameters {
  network: "city";
  seed: number;
  regime: string;
  policy: string;
  lead: number;
  pickup: string;
  hospital: string;
}
export interface GenerationJob {
  id: string;
  status: "queued" | "running" | "completed" | "failed";
  parameters: GenerationParameters;
  message?: string;
  error?: string;
  replay_url?: string;
}
export function generationParameters(
  seed: string,
  regime: string,
  policy: string,
  lead: number,
  pickup: string,
  hospital: string,
): GenerationParameters {
  const number = Number(seed);
  if (
    !seed.trim() ||
    !Number.isInteger(number) ||
    number < 0 ||
    number > 2147483647
  )
    throw new Error("Enter a whole-number seed from 0 to 2147483647.");
  if (
    !["sparse", "moderate", "asymmetric", "heavy"].includes(regime) ||
    !["fixed", "immediate", "analytical", "ordinary"].includes(policy) ||
    ![0, 5, 10, 20, 30].includes(lead)
  )
    throw new Error("Choose one of the supported policy and demand settings.");
  if (
    !/^P\d{3}$/.test(pickup) ||
    !["HOSP_WEST", "HOSP_EAST"].includes(hospital)
  )
    throw new Error(
      "Choose a canonical city pickup and hospital before generating.",
    );
  return {
    network: "city",
    seed: number,
    regime,
    policy,
    lead,
    pickup,
    hospital,
  };
}
export function validateJob(value: unknown): GenerationJob {
  const job = value as GenerationJob;
  if (
    !job ||
    !/^([a-f0-9]{32})$/.test(job.id) ||
    !["queued", "running", "completed", "failed"].includes(job.status) ||
    !job.parameters
  )
    throw new Error("The local server returned an invalid job record.");
  return job;
}
export async function localRequest(
  url: string,
  signal: AbortSignal,
  body?: unknown,
): Promise<unknown> {
  const response = await fetch(url, {
    method: body === undefined ? "GET" : "POST",
    headers:
      body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.any([signal, AbortSignal.timeout(30000)]),
  });
  const value = await boundedJson(response);
  if (!response.ok)
    throw new LocalResponseError(
      value && typeof value === "object" && "error" in value && typeof value.error === "string"
        ? value.error
        : `Local server returned ${response.status}.`,
      response.status,
    );
  return value;
}
export class LocalResponseError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}
export interface StoredRequest {
  id: string;
  parameters: GenerationParameters;
}
export function storedRequest(value: unknown): StoredRequest {
  const request = value as StoredRequest;
  if (!request || !/^([a-f0-9]{32})$/.test(request.id) || !request.parameters)
    throw new Error("Saved local request is invalid.");
  const p = request.parameters;
  if (p.network !== "city")
    throw new Error("Saved local request network is unsupported.");
  return {
    id: request.id,
    parameters: generationParameters(
      String(p.seed),
      p.regime,
      p.policy,
      p.lead,
      p.pickup,
      p.hospital,
    ),
  };
}

export function bindJob(
  job: GenerationJob,
  request: StoredRequest,
): GenerationJob {
  if (
    job.id !== request.id ||
    Object.entries(request.parameters).some(
      ([key, value]) =>
        job.parameters[key as keyof GenerationParameters] !== value,
    )
  )
    throw new Error(
      "The local job does not match the saved request identity and settings.",
    );
  return job;
}
