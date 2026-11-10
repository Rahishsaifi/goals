import assert from "node:assert/strict";
import test from "node:test";

import { FORECAST_DEFAULTS, productionForecast } from "../lib/production-forecast.ts";

test("two lakh resumes across five jobs sizes production search and database", () => {
  const forecast = productionForecast(FORECAST_DEFAULTS);
  assert.equal(forecast.parseCalls, 200_000);
  assert.equal(forecast.scoreCalls, 1_000_000);
  assert.equal(forecast.jobCalls, 5);

  const search = forecast.lines.find((line) => line.id === "search");
  const postgres = forecast.lines.find((line) => line.id === "postgres");
  assert.equal(search?.sku, "Basic");
  assert.match(postgres?.sku ?? "", /4 vCore/);
  assert.ok(forecast.modelBatchUsd > forecast.laterMonthUsd);
  assert.equal(
    forecast.thisMonthUsd,
    Math.round(forecast.lines.reduce((sum, line) => sum + line.thisMonthUsd, 0) * 100) / 100,
  );
});

test("a small corpus stays on free search and two vCores", () => {
  const forecast = productionForecast({
    ...FORECAST_DEFAULTS,
    resumes: 1_000,
    jobProfiles: 1,
    criteriaPerJob: 6,
  });
  assert.equal(forecast.scoreCalls, 1_000);
  assert.equal(forecast.lines.find((line) => line.id === "search")?.sku, "Free");
  assert.match(forecast.lines.find((line) => line.id === "postgres")?.sku ?? "", /2 vCore/);
});

test("monthly rescore repeats the model batch after the first month", () => {
  const once = productionForecast(FORECAST_DEFAULTS);
  const monthly = productionForecast({ ...FORECAST_DEFAULTS, rescoreMonthly: true });
  assert.equal(once.lines.find((line) => line.id === "openai")?.laterMonthUsd, 0);
  assert.equal(monthly.lines.find((line) => line.id === "openai")?.laterMonthUsd, monthly.modelBatchUsd);
});
