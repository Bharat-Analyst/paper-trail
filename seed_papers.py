"""
seed_papers.py — Curated canonical reading list for PaperPilot.

Papers are grouped into TIERS. A tier is a learning stage: tier 0 is pure
intuition, and each later tier assumes you've absorbed the ideas before it.
The tier number feeds directly into PaperPilot's "read order" so foundational
papers surface before advanced ones.

IMPORTANT — about arxiv_id:
The IDs below are my best-known values, but you should NOT trust them blindly.
On INIT, have the arXiv loader search arXiv by TITLE, confirm the match, and
use the ID/PDF link arXiv returns. That way a wrong ID here self-corrects, and
you always get a valid PDF. Every arXiv paper exposes:
    abstract page : https://arxiv.org/abs/<arxiv_id>
    PDF           : https://arxiv.org/pdf/<arxiv_id>
A few classics (e.g. the original GPT-1 report, AlexNet, Dropout) are NOT on
arXiv; those are marked arxiv_id=None and carry a `url` instead. Your loader
should handle both.
"""

SEED_PAPERS = [

    # === TIER 0 — Intuition & prerequisites (start here) ===
    {
        "title": "Efficient Estimation of Word Representations in Vector Space (word2vec)",
        "arxiv_id": "1301.3781",
        "tier": 0,
        "topic": "embeddings",
        "why": "Where 'words as vectors' comes from — the mental model behind all embeddings and RAG retrieval.",
    },
    {
        "title": "Sequence to Sequence Learning with Neural Networks",
        "arxiv_id": "1409.3215",
        "tier": 0,
        "topic": "foundations",
        "why": "The encoder-decoder idea that everything after attention builds on.",
    },
    {
        "title": "Adam: A Method for Stochastic Optimization",
        "arxiv_id": "1412.6980",
        "tier": 0,
        "topic": "optimization",
        "why": "The optimizer you'll see cited in nearly every training paper. Skim for the intuition only.",
    },

    # === TIER 1 — Core LLM (the backbone) ===
    {
        "title": "Attention Is All You Need",
        "arxiv_id": "1706.03762",
        "tier": 1,
        "topic": "transformers",
        "why": "THE paper. The Transformer. Read Jay Alammar's 'Illustrated Transformer' alongside it.",
    },
    {
        "title": "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding",
        "arxiv_id": "1810.04805",
        "tier": 1,
        "topic": "transformers",
        "why": "Pretraining + fine-tuning paradigm; the 'encoder' side of the family.",
    },
    {
        "title": "Language Models are Few-Shot Learners (GPT-3)",
        "arxiv_id": "2005.14165",
        "tier": 1,
        "topic": "llm",
        "why": "In-context learning — why prompting works at all. Long; first-pass it.",
    },
    {
        "title": "Scaling Laws for Neural Language Models",
        "arxiv_id": "2001.08361",
        "tier": 1,
        "topic": "llm",
        "why": "Why bigger + more data = better, and how predictably. Core vocabulary for the field.",
    },
    {
        "title": "Training Compute-Optimal Large Language Models (Chinchilla)",
        "arxiv_id": "2203.15556",
        "tier": 1,
        "topic": "llm",
        "why": "Corrected the scaling story — data matters more than people thought.",
    },
    {
        "title": "Emergent Abilities of Large Language Models",
        "arxiv_id": "2206.07682",
        "tier": 1,
        "topic": "llm",
        "why": "The 'capabilities appear suddenly at scale' idea. Short and conceptual.",
    },
    {
        "title": "LLaMA: Open and Efficient Foundation Language Models",
        "arxiv_id": "2302.13971",
        "tier": 1,
        "topic": "llm",
        "why": "The open-model lineage most local LLMs descend from.",
    },

    # === TIER 2 — RAG & retrieval ===
    {
        "title": "Dense Passage Retrieval for Open-Domain Question Answering (DPR)",
        "arxiv_id": "2004.04906",
        "tier": 2,
        "topic": "rag",
        "why": "How semantic retrieval actually works — the engine inside RAG.",
    },
    {
        "title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
        "arxiv_id": "2005.11401",
        "tier": 2,
        "topic": "rag",
        "why": "The RAG paper. Everything you built in Week 2 traces here.",
    },
    {
        "title": "REALM: Retrieval-Augmented Language Model Pre-Training",
        "arxiv_id": "2002.08909",
        "tier": 2,
        "topic": "rag",
        "why": "Retrieval baked into pretraining — a key alternative framing.",
    },
    {
        "title": "Leveraging Passage Retrieval with Generative Models for Open Domain QA (Fusion-in-Decoder)",
        "arxiv_id": "2007.01282",
        "tier": 2,
        "topic": "rag",
        "why": "How to feed many retrieved passages into a generator effectively.",
    },
    {
        "title": "Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks",
        "arxiv_id": "1908.10084",
        "tier": 2,
        "topic": "embeddings",
        "why": "The practical embedding models you'll actually use to build a vector store.",
    },
    {
        "title": "Precise Zero-Shot Dense Retrieval without Relevance Labels (HyDE)",
        "arxiv_id": "2212.10496",
        "tier": 2,
        "topic": "rag",
        "why": "A clever query-rewriting trick that noticeably improves retrieval.",
    },
    {
        "title": "Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection",
        "arxiv_id": "2310.11511",
        "tier": 2,
        "topic": "rag",
        "why": "Modern RAG that decides WHEN to retrieve and checks its own output.",
    },
    {
        "title": "Retrieval-Augmented Generation for Large Language Models: A Survey",
        "arxiv_id": "2312.10997",
        "tier": 2,
        "topic": "rag",
        "why": "A map of the whole RAG landscape. Great to skim once you've read the above.",
    },

    # === TIER 3 — Reasoning & agents ===
    {
        "title": "Chain-of-Thought Prompting Elicits Reasoning in Large Language Models",
        "arxiv_id": "2201.11903",
        "tier": 3,
        "topic": "reasoning",
        "why": "'Think step by step.' The root of LLM reasoning. Very readable.",
    },
    {
        "title": "ReAct: Synergizing Reasoning and Acting in Language Models",
        "arxiv_id": "2210.03629",
        "tier": 3,
        "topic": "agents",
        "why": "The backbone of tool-using agents. Read this one carefully.",
    },
    {
        "title": "Toolformer: Language Models Can Teach Themselves to Use Tools",
        "arxiv_id": "2302.04761",
        "tier": 3,
        "topic": "agents",
        "why": "How models learn to call tools/APIs — the core of function calling.",
    },
    {
        "title": "Reflexion: Language Agents with Verbal Reinforcement Learning",
        "arxiv_id": "2303.11366",
        "tier": 3,
        "topic": "agents",
        "why": "Agents that reflect on failures and retry — the 'self-correction' idea.",
    },
    {
        "title": "Tree of Thoughts: Deliberate Problem Solving with Large Language Models",
        "arxiv_id": "2305.10601",
        "tier": 3,
        "topic": "reasoning",
        "why": "Exploring multiple reasoning paths instead of one. Extends CoT.",
    },
    {
        "title": "Generative Agents: Interactive Simulacra of Human Behavior",
        "arxiv_id": "2304.03442",
        "tier": 3,
        "topic": "agents",
        "why": "Memory, planning, reflection in a multi-agent world. Famous and fun.",
    },
    {
        "title": "The Rise and Potential of Large Language Model Based Agents: A Survey",
        "arxiv_id": "2309.07864",
        "tier": 3,
        "topic": "agents",
        "why": "A structured overview of the whole agent space. Skim as a map.",
    },

    # === TIER 4 — Fine-tuning, alignment, efficiency (advanced) ===
    {
        "title": "LoRA: Low-Rank Adaptation of Large Language Models",
        "arxiv_id": "2106.09685",
        "tier": 4,
        "topic": "fine-tuning",
        "why": "How people cheaply fine-tune big models. Practical and widely used.",
    },
    {
        "title": "QLoRA: Efficient Finetuning of Quantized LLMs",
        "arxiv_id": "2305.14314",
        "tier": 4,
        "topic": "fine-tuning",
        "why": "Fine-tune large models on a single GPU. Builds directly on LoRA.",
    },
    {
        "title": "Training Language Models to Follow Instructions with Human Feedback (InstructGPT)",
        "arxiv_id": "2203.02155",
        "tier": 4,
        "topic": "alignment",
        "why": "RLHF — how raw models become helpful assistants.",
    },
    {
        "title": "Direct Preference Optimization: Your Language Model is Secretly a Reward Model (DPO)",
        "arxiv_id": "2305.18290",
        "tier": 4,
        "topic": "alignment",
        "why": "The simpler RLHF alternative that's now everywhere.",
    },
    {
        "title": "Constitutional AI: Harmlessness from AI Feedback",
        "arxiv_id": "2212.08073",
        "tier": 4,
        "topic": "alignment",
        "why": "Aligning models with a set of principles instead of human labels.",
    },
    {
        "title": "Mixtral of Experts",
        "arxiv_id": "2401.04088",
        "tier": 4,
        "topic": "architecture",
        "why": "Mixture-of-Experts — how you get big-model quality at lower inference cost.",
    },
]


def papers_by_tier():
    """Return seed papers grouped by tier, in reading order."""
    tiers = {}
    for p in SEED_PAPERS:
        tiers.setdefault(p["tier"], []).append(p)
    return dict(sorted(tiers.items()))


def abs_url(arxiv_id):
    return f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else None


def pdf_url(arxiv_id):
    return f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else None


if __name__ == "__main__":
    for tier, papers in papers_by_tier().items():
        print(f"\n=== TIER {tier} ({len(papers)} papers) ===")
        for p in papers:
            print(f"  [{p['topic']:12}] {p['title']}")
            print(f"                 {pdf_url(p['arxiv_id'])}")
    print(f"\nTotal: {len(SEED_PAPERS)} papers")
