import canonicalRun from "./fixtures/canonical-run-p0.json";
import { RunSchema } from "./schema";

export const canonicalRunFixture = RunSchema.parse(canonicalRun);
