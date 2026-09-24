# resumes/

Put the resumes you want to screen in this folder (`.pdf` or `.docx`), then run:

```bash
python main.py --input ./resumes --output ./output/results.json --report
```

Everything in this folder except this README is ignored by Git (see `.gitignore`), because resumes contain personal information. The resume dataset used for the documented production run is intentionally **not** included in the repository.

To try the pipeline without your own data, use the synthetic resumes in [`../samples/resumes/`](../samples/resumes/).
