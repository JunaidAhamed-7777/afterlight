import test from "node:test";
import assert from "node:assert/strict";
import { generationParameters, validateJob } from "../src/generation.ts";
test("canonical fixed-lead generation request preserves zero-lead distinction", () => {
  assert.deepEqual(
    generationParameters("7", "moderate", "fixed", 0, "P001", "HOSP_WEST"),
    {
      network: "city",
      seed: 7,
      regime: "moderate",
      policy: "fixed",
      lead: 0,
      pickup: "P001",
      hospital: "HOSP_WEST",
    },
  );
});
test("invalid seeds and unsupported route/policy values do not reach POST", () => {
  for (const seed of ["", "-1", "1.5", "x", "2147483648"])
    assert.throws(() =>
      generationParameters(seed, "moderate", "fixed", 10, "P001", "HOSP_WEST"),
    );
  assert.throws(() =>
    generationParameters("7", "moderate", "learned", 10, "P001", "HOSP_WEST"),
  );
  assert.throws(() =>
    generationParameters("7", "moderate", "fixed", 10, "fixture", "HOSP_WEST"),
  );
});
test("only known job state and safe ID accepted for polling", () => {
  assert.throws(() =>
    validateJob({ id: "../../secret", status: "running", parameters: {} }),
  );
  assert.throws(() =>
    validateJob({ id: "a".repeat(32), status: "maybe", parameters: {} }),
  );
  assert.equal(
    validateJob({ id: "a".repeat(32), status: "running", parameters: {} })
      .status,
    "running",
  );
});

test("saved idempotent request restores original settings without picking up later controls", async () => {
  const { storedRequest } = await import("../src/generation.ts");
  const parameters = generationParameters(
    "7",
    "moderate",
    "fixed",
    10,
    "P001",
    "HOSP_WEST",
  );
  const saved = storedRequest({ id: "a".repeat(32), parameters });
  parameters.seed = 42;
  assert.equal(saved.parameters.seed, 7);
  assert.equal(saved.id, "a".repeat(32));
  assert.throws(() => storedRequest({ id: "bad", parameters }));
});

test("status records stay bound to the requested ID and original parameters", async () => {
  const { bindJob } = await import("../src/generation.ts");
  const parameters = generationParameters(
    "7",
    "moderate",
    "fixed",
    10,
    "P001",
    "HOSP_WEST",
  );
  const request = { id: "a".repeat(32), parameters };
  const job = {
    id: request.id,
    status: "running" as const,
    parameters: { ...parameters },
  };
  assert.equal(bindJob(job, request), job);
  assert.throws(
    () => bindJob({ ...job, id: "b".repeat(32) }, request),
    /does not match/,
  );
  assert.throws(
    () =>
      bindJob(
        { ...job, parameters: { ...parameters, pickup: "P002" } },
        request,
      ),
    /does not match/,
  );
});
