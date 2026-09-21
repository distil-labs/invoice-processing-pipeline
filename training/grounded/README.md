# Grounded decision model (step 2b, used by the pipeline)

Fine-tuned `Qwen3.5-4B` that makes the same pay-or-hold decision and also says what is wrong and where: the invoice number, the PO number, the item, and the two values that disagree.

Output:

```json
{"decision": "hold_price", "invoice_number": "NM-84665", "po_number": "PO-48825", "item": "Floor marking tape, yellow", "invoiced": 14.61, "expected": 14.25}
```

The trained model: [distil-labs/distil-qwen3.5-4b-invoice-grounded-decision](https://huggingface.co/distil-labs/distil-qwen3.5-4b-invoice-grounded-decision) (safetensors) and [distil-labs/distil-qwen3.5-4b-invoice-grounded-decision-gguf](https://huggingface.co/distil-labs/distil-qwen3.5-4b-invoice-grounded-decision-gguf) (Q8_0 GGUF for llama.cpp).

## Files

| File | What it is |
|---|---|
| `job_description.json` | The task prompt (`task_description`, which is also the system prompt the model is served with), the judge instructions, and the instructions for synthetic data generation |
| `config.yaml` | Student and teacher model, task type, and the mutators that steer synthetic data generation |
| `train.jsonl` | Seed examples: the same 40 cases as the decision model, with the six-field answer and the same written-out reasoning |
| `test.jsonl` | Test set: the same 100 cases. The teacher never sees it |

## Setup used

| | |
|---|---|
| Student | `Qwen3.5-4B` |
| Teacher | `zai.glm-5.3-high-thinking` |
| Task type | `question-answering` with `synthgen.output_is_json: true` |
| Thinking | on |
| Synthetic examples generated | 4,056 |
| Mutators | the decision model's six, plus `order_size` (small, typical, large orders) |
| Result | 97 / 100 with all six fields right and 99 / 100 decisions (the untuned model scores 0.12 on the platform's judge). |

`base.enable_thinking: true` makes the teacher write the reasoning for every synthetic example and trains, evaluates and serves the student with thinking on. The reasoning format is taught by example: every row of `train.jsonl` carries a `reasoning_content` field (checks in policy order, one short line per invoice line, a running sum, stop at the first failure), and `synthetic_data_generation_instructions` in `job_description.json` describes the same format in words. Keep both if you change the policy.

## Train it on distil labs

Install the CLI and sign in:

```bash
curl -fsSL https://cli-assets.distillabs.ai/install.sh | sh
distil auth            # or: distil signup
```

Upload this directory, check that the teacher can do the task, generate the training data, train:

```bash
distil seed-dataset create --data training/grounded                        # prints the seed dataset id
distil teacher-evaluation create-from-seed-dataset <seed-dataset-id>     # feasibility check on test.jsonl
distil training-dataset create-from-seed-dataset <seed-dataset-id>       # synthetic data generation
distil slm create-from-training-dataset <training-dataset-id>            # fine-tuning, then evaluation of the base and the tuned model
```

Follow a job with `distil <group> status <id>` and read its scores with `distil <group> metrics <id>`. Before the full generation run it is worth running a small one and reading the output: download the expanded config with `distil seed-dataset download-metadata`, set `synthgen.generation_target` to about 200, and pass it with `--config`.

Get the model:

```bash
distil slm download -d artifacts/grounded <slm-id>          # model.tar with the merged weights
distil deployment create-from-slm <slm-id>                # or serve it on the platform
```

To run it with llama.cpp, convert the extracted `model/` directory to GGUF as described in the main README.

## Adapting it

Change the task in `job_description.json`, replace `train.jsonl` and `test.jsonl` with your own examples in the same chat format (one user message, one assistant message holding the JSON answer), and adjust the mutators in `config.yaml` to the variety your inputs have. The task description is the system prompt the model is trained and served with, so keep it identical between training and inference.
