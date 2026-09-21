# Triage model (step 1)

Fine-tuned `Qwen3.5-0.8B` that labels a message sent to the accounts payable inbox as `invoice`, `receipt`, `payment_reminder`, `vendor_other` or `spam`.

Output:

```json
{"label": "payment_reminder"}
```

## Files

| File | What it is |
|---|---|
| `job_description.json` | The task prompt (`task_description`, which is also the system prompt the model is served with), the judge instructions, and the instructions for synthetic data generation |
| `config.yaml` | Student and teacher model, task type, and the mutators that steer synthetic data generation |
| `train.jsonl` | Seed examples: 40 messages: 12 invoices and 7 of each other label, including misleading ones (reminders that quote the invoice, paid copies, lookalike-domain phishing, injected instructions) |
| `test.jsonl` | Test set: 200 messages: 100 invoices and 25 of each other label, 49 of them misleading. The teacher never sees it |

## Setup used

| | |
|---|---|
| Student | `Qwen3.5-0.8B` |
| Teacher | `zai.glm-5.3-high-thinking` |
| Task type | `question-answering` with `synthgen.output_is_json: true` |
| Thinking | off |
| Synthetic examples generated | 3,124 |
| Mutators | `label` (weighted), `difficulty` (plain, easy to confuse with another label, carrying an injected instruction), `wrapper` (sent directly, or forwarded by an employee) |
| Result | 200 / 200 on the test set (the untuned model scores 0.70 on the platform's judge). Qwen3.5-2B trained on the same data also reaches 200 / 200. |

## Train it on distil labs

Install the CLI and sign in:

```bash
curl -fsSL https://cli-assets.distillabs.ai/install.sh | sh
distil auth            # or: distil signup
```

Upload this directory, check that the teacher can do the task, generate the training data, train:

```bash
distil seed-dataset create --data training/triage                        # prints the seed dataset id
distil teacher-evaluation create-from-seed-dataset <seed-dataset-id>     # feasibility check on test.jsonl
distil training-dataset create-from-seed-dataset <seed-dataset-id>       # synthetic data generation
distil slm create-from-training-dataset <training-dataset-id>            # fine-tuning, then evaluation of the base and the tuned model
```

Follow a job with `distil <group> status <id>` and read its scores with `distil <group> metrics <id>`. Before the full generation run it is worth running a small one and reading the output: download the expanded config with `distil seed-dataset download-metadata`, set `synthgen.generation_target` to about 200, and pass it with `--config`.

Get the model:

```bash
distil slm download -d artifacts/triage <slm-id>          # model.tar with the merged weights
distil deployment create-from-slm <slm-id>                # or serve it on the platform
```

To run it with llama.cpp, convert the extracted `model/` directory to GGUF as described in the main README.

## Adapting it

Change the task in `job_description.json`, replace `train.jsonl` and `test.jsonl` with your own examples in the same chat format (one user message, one assistant message holding the JSON answer), and adjust the mutators in `config.yaml` to the variety your inputs have. The task description is the system prompt the model is trained and served with, so keep it identical between training and inference.
