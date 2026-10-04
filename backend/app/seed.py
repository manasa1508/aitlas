"""Small, reviewed starter corpus. Claims are deliberately narrow and source linked."""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .models import Company, Evidence, Knowledge, Opportunity, UseCase


KNOWLEDGE = [
    ("attention-2014", "Attention for neural translation", 2014, "NLP", "Bahdanau, Cho and Bengio introduced soft alignment that lets a translation model focus on relevant parts of an input sequence.", "https://arxiv.org/abs/1409.0473", "Original paper", ["attention", "translation"], ["transformer-2017"]),
    ("resnet-2015", "Residual networks", 2015, "Vision", "Residual connections made substantially deeper image recognition networks easier to train.", "https://arxiv.org/abs/1512.03385", "Original paper", ["deep learning", "vision"], []),
    ("transformer-2017", "The Transformer", 2017, "NLP", "Attention Is All You Need proposed a sequence model built around attention rather than recurrence or convolution.", "https://arxiv.org/abs/1706.03762", "Original paper", ["attention", "architecture", "LLM"], ["attention-2014", "bert-2018", "gpt3-2020"]),
    ("bert-2018", "BERT", 2018, "NLP", "BERT showed how bidirectional Transformer pretraining could transfer to a range of language understanding tasks.", "https://arxiv.org/abs/1810.04805", "Original paper", ["transformer", "pretraining"], ["transformer-2017"]),
    ("gpt3-2020", "Few-shot language models", 2020, "LLMs", "The GPT-3 paper studied how a scaled language model could perform tasks from instructions or a few examples without task-specific gradient updates.", "https://arxiv.org/abs/2005.14165", "Original paper", ["LLM", "few-shot"], ["transformer-2017"]),
    ("rag-2020", "Retrieval-augmented generation", 2020, "LLMs", "RAG combined a language model with retrieval from an external knowledge index for knowledge-intensive tasks.", "https://arxiv.org/abs/2005.11401", "Original paper", ["RAG", "retrieval"], ["gpt3-2020"]),
    ("lora-2021", "LoRA", 2021, "LLMs", "Low-rank adaptation reduced the number of trainable parameters needed to adapt large pretrained models.", "https://arxiv.org/abs/2106.09685", "Original paper", ["fine-tuning", "LLM"], ["transformer-2017", "qlora-2023"]),
    ("qlora-2023", "QLoRA", 2023, "LLMs", "QLoRA combined low-rank adapters with quantization to reduce memory use during large-model fine-tuning.", "https://arxiv.org/abs/2305.14314", "Original paper", ["fine-tuning", "quantization"], ["lora-2021"]),
]

COMPANIES = [
    ("klarna", "Klarna", "Financial services", "Evidence in this profile concerns Klarna's reported AI customer service deployment. Results are vendor-reported and may change.", "https://www.klarna.com/"),
    ("accenture", "Accenture", "Professional services", "Evidence in this profile concerns a published GitHub Copilot enterprise study.", "https://www.accenture.com/"),
    ("deepmind", "Google DeepMind", "AI research", "Evidence in this profile concerns AlphaFold and its public protein structure database.", "https://deepmind.google/"),
]

EVIDENCE = [
    ("klarna-assistant", "klarna", "AI customer assistant", "OpenAI's Klarna case study reports a multilingual assistant for support, returns and refunds; reported outcomes are from the first month of operation.", "https://openai.com/index/klarna/", "OpenAI customer story"),
    ("accenture-copilot", "accenture", "Developer AI study", "GitHub published research with Accenture on Copilot use and developer experience in an enterprise setting.", "https://github.blog/news-insights/research/research-quantifying-github-copilots-impact-in-the-enterprise-with-accenture/", "GitHub research"),
    ("deepmind-alphafold", "deepmind", "AlphaFold database", "Google DeepMind says AlphaFold's structure predictions are shared through a public database with EMBL-EBI.", "https://deepmind.google/blog/alphafold-reveals-the-structure-of-the-protein-universe/", "Google DeepMind"),
]

CASES = [
    ("klarna-support", "klarna", "Multilingual customer support assistant", "Financial services", "Customer operations", "Klarna deployed an AI assistant across customer service flows including returns and refunds.", "The vendor case study reports 2.3 million conversations in its first month and a 25% drop in repeat inquiries. Treat these as company-reported results.", "https://openai.com/index/klarna/", "OpenAI customer story", "Production, company reported", ["support", "LLM", "multilingual"]),
    ("accenture-dev", "accenture", "AI pair programming in enterprise development", "Professional services", "Developer tools", "A published enterprise study examined GitHub Copilot adoption and developer experience at Accenture.", "The study reports developer experience and productivity findings; review the methodology before generalizing them.", "https://github.blog/news-insights/research/research-quantifying-github-copilots-impact-in-the-enterprise-with-accenture/", "GitHub research", "Research study", ["coding", "productivity"]),
    ("alphafold-science", "deepmind", "Protein structure predictions at scale", "Life sciences", "Scientific discovery", "AlphaFold predicts protein structures and shares predictions through a public database.", "The AlphaFold database broadened access to protein structure predictions; downstream research impact varies by use.", "https://deepmind.google/blog/alphafold-reveals-the-structure-of-the-protein-universe/", "Google DeepMind", "Production research infrastructure", ["biology", "vision", "science"]),
]

OPPORTUNITIES = [
    ("regulated-support", "Auditable AI support in regulated workflows", "Financial services", "Customer operations", "Hypothesis: teams may need support assistants that link each answer to approved policy and provide a clear escalation trail.", "Policy change control, privacy and human review make implementation harder than a general chatbot.", "https://openai.com/index/klarna/", "Klarna deployment provides adjacent evidence"),
    ("research-provenance", "Provenance for scientific AI outputs", "Life sciences", "Scientific discovery", "Hypothesis: researchers may value tools that connect model predictions to source datasets, versions and validation steps.", "Scientific validation, data licensing and reproducibility are substantial barriers.", "https://deepmind.google/blog/alphafold-reveals-the-structure-of-the-protein-universe/", "AlphaFold database provides adjacent evidence"),
    ("dev-ai-review", "Review workflows for AI-generated code", "Software", "Developer tools", "Hypothesis: teams adopting coding assistants may need richer review, security and measurement workflows.", "Access to proprietary code, trust and integration with existing developer tooling are barriers.", "https://github.blog/news-insights/research/research-quantifying-github-copilots-impact-in-the-enterprise-with-accenture/", "Copilot enterprise study provides adjacent evidence"),
]


def seed(session: Session) -> None:
    for id_, title, year, category, summary, url, label, tags, related in KNOWLEDGE:
        if not session.get(Knowledge, id_):
            session.add(Knowledge(id=id_, title=title, year=year, category=category, summary=summary, source_url=url, source_label=label, tags=tags, related_ids=related))
    for id_, name, industry, summary, website in COMPANIES:
        if not session.get(Company, id_):
            session.add(Company(id=id_, name=name, industry=industry, summary=summary, website=website))
    session.flush()
    for id_, company_id, title, claim, url, label in EVIDENCE:
        if not session.get(Evidence, id_):
            session.add(Evidence(id=id_, company_id=company_id, title=title, claim=claim, source_url=url, source_label=label))
    for id_, company_id, title, industry, domain, summary, outcome, url, label, maturity, tags in CASES:
        if not session.get(UseCase, id_):
            session.add(UseCase(id=id_, company_id=company_id, title=title, industry=industry, domain=domain, summary=summary, outcome=outcome, evidence_url=url, evidence_label=label, maturity=maturity, tags=tags))
    for id_, title, industry, capability, thesis, barrier, url, label in OPPORTUNITIES:
        if not session.get(Opportunity, id_):
            session.add(Opportunity(id=id_, title=title, industry=industry, capability=capability, thesis=thesis, barrier=barrier, evidence_url=url, evidence_label=label, status="hypothesis"))
    session.commit()
