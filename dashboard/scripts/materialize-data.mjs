import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

// CI and offline builds validate the data already present in their checkout.
if (process.env.AXIOM_ORACLES_DATA_SOURCE === "checkout") {
  process.exit(0);
}

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const helper = join(repositoryRoot, "scripts", "oracle_data.py");

// Dashboard uploads and archives carry public/data without the surrounding
// source repository or Python tooling. Keep their bundled snapshot usable.
if (!existsSync(helper) || !existsSync(join(repositoryRoot, ".git"))) {
  console.log("Using bundled oracle data; source Git checkout is unavailable.");
} else {
  const projectPython = join(repositoryRoot, ".venv", "bin", "python");
  const python = existsSync(projectPython) ? projectPython : "python3";
  try {
    execFileSync(python, [helper, "materialize"], {
      cwd: repositoryRoot,
      stdio: "inherit",
    });
  } catch (error) {
    if (!Number.isInteger(error.status)) {
      console.error(`Unable to materialize oracle data: ${error.message}`);
    }
    process.exit(Number.isInteger(error.status) ? error.status : 1);
  }
}
