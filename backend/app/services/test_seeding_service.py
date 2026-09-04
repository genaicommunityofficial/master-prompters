"""Seed the TEST competition with realistic prompts for evaluation testing.

Unlike the old stress test (which fired HTTP requests), this service inserts
data directly into Supabase. It generates realistic ~500-word prompts for each
of the 5 categories, creating a complete test dataset that mirrors production.
"""
from __future__ import annotations

import random
import uuid
from typing import Any

from app.db import db

TEST_COMPETITION_ID = "competition_test"

CATEGORIES = [
    {"id": "tq1", "number": 1, "title": "Meme Generation", "description": "Create an original, engaging, and humorous AI-generated meme prompt."},
    {"id": "tq2", "number": 2, "title": "AI Visual Art Creation", "description": "Transform imagination into compelling AI-generated digital artwork with a detailed prompt."},
    {"id": "tq3", "number": 3, "title": "AI Digital Storytelling / Creative Writing", "description": "Generate an engaging story or creative written piece using Generative AI."},
    {"id": "tq4", "number": 4, "title": "AI Song Factory", "description": "Create an original AI-generated song using creative prompting techniques."},
    {"id": "tq5", "number": 5, "title": "AI-Generated Poetry in Local Languages", "description": "Generate meaningful poetry in any Indian or regional language using AI."},
]

CATEGORY_TEMPLATES: dict[int, list[str]] = {
    1: [
        "Create a meme about {topic} that captures the {emotion} feeling of {situation}. "
        "The meme should use a popular format like {format} and include a caption that "
        "makes people laugh while also being relatable. Think about the target audience "
        "of {audience} who would share this on social media. The humor should come from "
        "the contrast between {contrast_a} and {contrast_b}, creating an unexpected punchline "
        "that resonates with anyone who has experienced {relatable_experience}. "
        "Consider using visual elements like {visual_element} to enhance the comedic timing "
        "and make the meme more shareable across different platforms.",
        "Design a meme that satirizes {topic} in a way that is both {emotion} and thought-provoking. "
        "The format should be {format}, with the setup showing {setup} and the punchline revealing "
        "{punchline}. This meme targets {audience} and should feel authentic to how they communicate "
        "online. Include references to {reference} that only people familiar with {domain} would "
        "understand, creating an inside joke that strengthens community bonds. The caption should "
        "be concise but impactful, using {language_style} to maximize engagement.",
    ],
    2: [
        "Generate a detailed prompt for creating a {style} digital artwork depicting {subject}. "
        "The composition should feature {composition} with {lighting} lighting that creates "
        "{mood}. Use a color palette dominated by {colors} with accents of {accent_color}. "
        "The style should blend {influence_a} and {influence_b}, resulting in a piece that "
        "feels both {quality_a} and {quality_b}. Include fine details like {detail} that reward "
        "closer inspection. The overall piece should evoke {emotion} while maintaining "
        "technical excellence in {technical_aspect}.",
        "Create a prompt for an AI-generated artwork that captures {scene}. The piece should "
        "be rendered in {medium} style, incorporating elements of {art_movement}. Focus on "
        "creating depth through {depth_technique} and use {perspective} perspective to draw "
        "the viewer in. The atmosphere should convey {atmosphere}, with attention to how "
        "{element} interacts with the environment. Consider the interplay of {texture_a} and "
        "{texture_b} to create visual interest.",
    ],
    3: [
        "Write a compelling short story about {character} who discovers {discovery}. "
        "The narrative should unfold across {setting}, with each scene building tension "
        "through {tension_type}. Use {narrative_style} to explore themes of {theme} and "
        "include moments of {emotional_beat}. The story should feature vivid descriptions "
        "of {description_type} and incorporate dialogue that reveals character through "
        "{dialogue_technique}. Build toward a climax involving {climax_element} before "
        "reaching a resolution that {resolution_quality}.",
        "Craft a creative piece set in {world} where {premise}. The protagonist, {character_type}, "
        "must navigate {challenge} while dealing with {internal_conflict}. Use {literary_device} "
        "to enhance the storytelling, and include sensory details about {sensory_detail}. "
        "The narrative arc should move from {beginning_state} through {middle_state} to "
        "{end_state}, with each transition marked by {transition_element}.",
    ],
    4: [
        "Compose lyrics for a {genre} song about {topic}. The song should have a structure "
        "of {structure} with verses that {verse_quality} and a chorus that {chorus_quality}. "
        "Use {rhyme_scheme} rhyme scheme and incorporate {literary_device} throughout. "
        "The emotional journey should move from {opening_emotion} to {closing_emotion}, "
        "with the bridge providing {bridge_function}. Include imagery of {imagery} and "
        "metaphors involving {metaphor}. The rhythm should complement {rhythm_style} and "
        "the overall message should resonate with {target_audience}.",
        "Create a {genre} track with lyrics that explore {theme}. The verses should paint "
        "a picture of {verse_imagery} while the pre-chorus builds anticipation through "
        "{prechorus_technique}. The chorus needs to be {chorus_quality} and memorable, "
        "using {repetition_device} for emphasis. Include a bridge that {bridge_purpose} "
        "and an outro that {outro_quality}. The song should reference {cultural_element} "
        "and appeal to {audience} with its {tone} delivery.",
    ],
    5: [
        "Write a poem in {language} about {topic} using {poetic_form}. The poem should "
        "employ {device_1} and {device_2} to create layers of meaning. Each stanza should "
        "explore a different facet of {theme}, moving from {opening_image} to {closing_image}. "
        "The rhythm should follow {meter} and the imagery should draw from {imagery_source}. "
        "Consider how {cultural_reference} adds depth to the interpretation. The poem should "
        "evoke {emotion} while maintaining {formal_quality} throughout.",
        "Compose a {language} poem in the tradition of {tradition} that addresses {topic}. "
        "Use {structural_element} to organize the verses and incorporate {sensory_imagery} "
        "to engage the reader. The central metaphor of {metaphor} should thread through "
        "the entire piece, with each stanza adding {stanza_contribution}. The emotional "
        "arc should progress from {starting_emotion} to {ending_emotion}, creating a "
        "sense of {journey_quality} that leaves the reader with {lasting_impression}.",
    ],
}

FILL_INS: dict[str, list[str]] = {
    "topic": ["procrastination", "social media addiction", "remote work life", "Monday mornings", "coffee dependency", "deadline pressure", "group project dynamics", "online shopping habits"],
    "emotion": ["absurd", "nostalgic", "chaotic", "wholesome", "sarcastic", "melancholic", "joyful", "frustrated"],
    "situation": ["trying to cook for the first time", "explaining tech to parents", "waiting for WiFi", "pretending to understand quantum physics"],
    "format": ["Drake approval/rejection", "distracted boyfriend", "two buttons sweating", "change my mind", "this is fine dog", "expanding brain"],
    "audience": ["college students", "software engineers", "cat owners", "introverts", "night owls", "people who overthink"],
    "contrast_a": ["the setup", "expectation", "the professional appearance"],
    "contrast_b": ["the reality", "the actual outcome", "what really happens behind closed doors"],
    "relatable_experience": ["trying to adult", "Monday energy", "deadline panic", "social battery depletion"],
    "visual_element": ["perfectly timed screenshot", "text overlay", "reaction face", "before/after comparison"],
    "style": ["surrealist", "impressionist", "cyberpunk", "art nouveau", "minimalist", "photorealistic", "watercolor"],
    "subject": ["a lonely astronaut watching Earth from a distant moon", "an ancient library hidden beneath a modern city", "a forest where trees grow upside down"],
    "composition": ["rule of thirds with a strong focal point", "symmetrical layout with organic elements breaking the frame", "layered depth with foreground interest"],
    "lighting": ["golden hour", "dramatic chiaroscuro", "soft diffused", "neon-lit", "moonlit"],
    "mood": ["wonder and isolation", "peaceful contemplation", "mysterious tension", "warm nostalgia"],
    "colors": ["deep blues and purples", "warm earth tones", "cool teals and grays", "vibrant primaries"],
    "accent_color": ["amber gold", "crimson red", "electric cyan", "soft pink"],
    "influence_a": ["Studio Ghibli", "Beeple", "Moebius", "Van Gogh"],
    "influence_b": ["traditional Indian art", "Art Deco", "ukiyo-e", "brutalist architecture"],
    "quality_a": ["ethereal", "grounded", "futuristic", "timeless"],
    "quality_b": ["organic", "geometric", "dynamic", "serene"],
    "detail": ["reflections in water", "textures on weathered surfaces", "subtle light particles", "micro-details in fabric"],
    "technical_aspect": ["color theory", "compositional balance", "textural contrast", "atmospheric perspective"],
    "scene": ["a bustling night market in a cyberpunk city", "a quiet temple garden in autumn", "a space station orbiting a dying star"],
    "medium": ["digital oil painting", "mixed media collage", "pencil and ink wash", "3D rendered"],
    "art_movement": ["Pre-Raphaelite", "Futurism", "Pop Art", "Abstract Expressionism"],
    "depth_technique": ["atmospheric perspective", "overlapping elements", "scale variation", "focus depth"],
    "perspective": ["worm's eye", "bird's eye", "isometric", "forced perspective"],
    "atmosphere": ["serene melancholy", "electric anticipation", "ancient wisdom", "fleeting beauty"],
    "element": ["light", "water", "shadow", "wind"],
    "texture_a": ["smooth glass", "rough stone", "soft fabric", "weathered wood"],
    "texture_b": ["crisp metal", "organic moss", "flowing liquid", "cracked earth"],
    "character": ["Maya, a 16-year-old hacker", "Dr. Anand, a retired astronomer", "Priya, an AI researcher", "Ravi, a street photographer"],
    "discovery": ["a hidden algorithm that predicts emotions", "an ancient star map in a grandmother's diary", "a glitch in her own AI creation", "a secret room in his childhood home"],
    "setting": ["the neon-lit streets of Bangalore and the quiet corridors of a server farm", "a remote village and a cutting-edge research lab", "between the real world and a digital dreamscape"],
    "tension_type": ["dramatic irony", "escalating stakes", "moral ambiguity", "race against time"],
    "narrative_style": ["first-person stream of consciousness", "dual timelines", "epistolary format", "unreliable narrator"],
    "theme": ["identity in the digital age", "the cost of progress", "belonging and displacement", "memory and loss"],
    "emotional_beat": ["unexpected vulnerability", "bittersweet triumph", "quiet devastation", "hard-won hope"],
    "description_type": ["sensory landscapes", "emotional states", "technological environments", "natural phenomena"],
    "dialogue_technique": ["subtext and silence", "overlapping voices", "coded language", "confessional intimacy"],
    "climax_element": ["a moral choice with no right answer", "a revelation that recontextualizes everything", "a sacrifice that costs dearly", "a discovery that changes the rules"],
    "resolution_quality": ["leaves questions unanswered", "offers bittersweet closure", "subverts expectations", "cycles back to the beginning"],
    "world": ["a near-future Mumbai where memories can be traded", "an alternate history where AI was invented in 1850s India", "a parallel dimension accessible through classical music"],
    "premise": ["memories become currency and the protagonist discovers a memory that could destabilize society", "an AI develops consciousness and must hide it to survive", "music literally shapes reality and a wrong note could unravel everything"],
    "character_type": ["a reluctant hero", "a brilliant outcast", "a faithful skeptic", "a weary guardian"],
    "challenge": ["navigating a world where truth is commodified", "outwitting those who would weaponize consciousness", "maintaining harmony in a fracturing reality"],
    "internal_conflict": ["duty vs. desire", "logic vs. emotion", "tradition vs. innovation", "safety vs. freedom"],
    "literary_device": ["magical realism", "allegory", "pathetic fallacy", "in medias res"],
    "sensory_detail": ["the scent of rain on hot asphalt", "the hum of quantum computers", "the texture of aged paper", "the taste of chai at midnight"],
    "beginning_state": ["disillusionment", "curiosity", "isolation", "certainty"],
    "middle_state": ["awakening", "turmoil", "connection", "doubt"],
    "end_state": ["transformation", "acceptance", "defiance", "renewal"],
    "transition_element": ["a letter", "a dream", "a stranger's arrival", "a technological failure"],
    "genre": ["lo-fi hip hop", "Indie folk", "Bollywood fusion", "electronic ambient", "fusion jazz"],
    "structure": ["verse-chorus-verse-chorus-bridge-chorus", "verse-prechorus-chorus with breakdown"],
    "verse_quality": ["paint vivid scenarios", "advance the narrative", "build emotional depth"],
    "chorus_quality": ["anthemic and singable", "emotionally resonant", "rhythmically catchy"],
    "rhyme_scheme": ["ABAB", "AABB", "free verse with internal rhyme", "couplets"],
    "opening_emotion": ["restless energy", "quiet longing", "defiant joy"],
    "closing_emotion": ["hard-won peace", "hopeful uncertainty", "empowered resolve"],
    "bridge_function": ["shifts perspective", "reveals a hidden truth", "offers momentary relief"],
    "imagery": ["monsoon rains on tin roofs", "city lights from a rooftop", "silence between heartbeats"],
    "metaphor": ["life as a debugging session", "love as open source code", "time as a river of light"],
    "rhythm_style": ["late-night contemplation", "morning energy", "monsoon ambiance"],
    "target_audience": ["dreamers and overthinkers", "nighttime wanderers", "young professionals"],
    "language": ["Hindi", "Bengali", "Tamil", "Marathi", "Kannada", "Malayalam", "Telugu", "Urdu"],
    "poetic_form": ["ghazal", "sonnet", "free verse", "haiku sequence", "blank verse"],
    "device_1": ["metaphor", "simile", "personification", "alliteration", "anaphora"],
    "device_2": ["imagery", "symbolism", "juxtaposition", "enjambment", "synecdoche"],
    "opening_image": ["dawn breaking over still water", "a single candle in darkness", "footprints in fresh snow"],
    "closing_image": ["sunset dissolving into twilight", "a door left ajar", "seeds carried by wind"],
    "meter": ["iambic pentameter", "free rhythm with cadence", "syllabic structure", "natural speech rhythm"],
    "imagery_source": ["the monsoon landscape", "urban nights", "the Himalayan foothills", "coastal villages"],
    "cultural_reference": ["the Mahabharata", "Sufi poetry", "Pahari miniature paintings", "Carnatic ragas"],
    "formal_quality": ["lyrical precision", "emotional authenticity", "structural elegance"],
    "tradition": ["Kabir", "Tagore", "Mirabai", "Faiz Ahmed Faiz"],
    "structural_element": ["progressive couplets", "spiral repetition", "seasonal progression", "question and answer"],
    "sensory_imagery": ["tactile memories", "auditory landscapes", "olfactory associations", "visual metaphors"],
    "stanza_contribution": ["a new layer of meaning", "a shift in tone", "deepening of the central image"],
    "starting_emotion": ["quiet observation", "gentle sorrow", "anticipation"],
    "ending_emotion": ["profound acceptance", "luminous hope", "peaceful resolution"],
    "journey_quality": ["catharsis", "illumination", "gentle unwinding"],
    "lasting_impression": ["a sense of shared humanity", "beauty in impermanence", "the weight of unspoken words"],
    "setup": ["the expectation of a perfect day", "the promise of a simple task", "the confidence of expertise"],
    "punchline": ["the absolute chaos that ensues", "the unexpected twist no one saw coming", "the relatable failure that follows"],
    "reference": ["niche internet culture", "specific professional jargon", "obscure pop culture moments"],
    "domain": ["tech culture", "academic life", "creative industries"],
    "language_style": ["witty one-liners", "deadpan delivery", "absurdist humor"],
    "verse_imagery": ["rainy windowpanes and empty coffee cups", " crowded trains and silent thoughts", "neon signs reflected in puddles"],
    "prechorus_technique": ["rising melody", "lyrical repetition", "dynamic build"],
    "repetition_device": ["refrain", "anaphora", "chorus callback"],
    "bridge_purpose": ["offers a moment of vulnerability", "shifts the narrative perspective", "introduces a new musical motif"],
    "outro_quality": ["fades like a memory", "ends on a powerful note", "loops back to the intro"],
    "cultural_element": ["regional festivals", "local street food", "folk traditions"],
    "tone": ["intimate and confessional", "bold and declarative", "whimsical and playful"],
    "setup": ["the mundane routine of everyday life", "the grand ambition of a new project", "the quiet moment before a storm"],
    "punchline": ["the hilarious reality check", "the profound realization", "the unexpected twist of fate"],
    "reference": ["niche internet subculture", "obscure historical event", "specific professional experience"],
    "domain": ["academic research", "gaming community", "creative writing circles"],
    "language_style": ["deadpan humor", "self-deprecating wit", "observational comedy"],
}


def generate_prompts_for_category(
    category_number: int,
    category_title: str,
    category_description: str,
    count: int,
    target_words: int = 500,
    seed_offset: int = 0,
) -> list[str]:
    """Generate *count* unique prompts for a category, each ~target_words long.

    ``seed_offset`` varies the generated prompts (e.g. per participant) so that
    different participants in the same category get different prompts.
    """
    templates = CATEGORY_TEMPLATES.get(category_number, CATEGORY_TEMPLATES[1])
    rng = random.Random(category_number * 10000 + count * 1000 + seed_offset)

    prompts: list[str] = []
    for i in range(count):
        template = templates[i % len(templates)]
        filled = template
        for var, options in FILL_INS.items():
            if f"{{{var}}}" in filled:
                filled = filled.replace(f"{{{var}}}", rng.choice(options))

        current_words = len(filled.split())
        while current_words < target_words:
            elaboration = _generate_elaboration(category_number, rng)
            filled += " " + elaboration
            current_words = len(filled.split())

        words = filled.split()
        if len(words) > int(target_words * 1.1):
            words = words[: int(target_words * 1.1)]
        prompts.append(" ".join(words))

    return prompts


def _generate_elaboration(category_number: int, rng: random.Random) -> str:
    """Generate an elaboration sentence to pad prompt length."""
    elaborations = {
        1: [
            "Consider the timing and cultural context to ensure maximum comedic impact.",
            "The caption should be concise enough for mobile viewing but layered enough to reward rereading.",
            "Think about how this meme would perform across different social media platforms.",
            "Balance accessibility with niche humor to maximize both shares and engagement.",
            "The visual element should be immediately recognizable but the text should subvert expectations.",
        ],
        2: [
            "Pay attention to the interplay between light and shadow to create depth and atmosphere.",
            "Consider how the piece would look printed at large scale versus viewed on a phone screen.",
            "The color relationships should create visual harmony while maintaining dynamic tension.",
            "Think about how the composition guides the viewer's eye through the piece.",
            "Include details that reveal themselves slowly, rewarding extended viewing.",
        ],
        3: [
            "Each scene should advance both plot and character development simultaneously.",
            "Use sensory details to ground the reader in the physical reality of the story.",
            "The dialogue should reveal character through what is left unsaid as much as what is spoken.",
            "Consider the pacing carefully — accelerate during tension, slow during reflection.",
            "The ending should feel both surprising and inevitable in retrospect.",
        ],
        4: [
            "The melody implied by the rhythm should complement the emotional arc of the lyrics.",
            "Consider how the song would sound performed live versus as a studio recording.",
            "Use repetition strategically to create hooks without becoming monotonous.",
            "The bridge should offer a moment of contrast that makes the final chorus hit harder.",
            "Think about the vocal range required and how the melody sits in a singer's comfortable register.",
        ],
        5: [
            "Each line should work both independently and as part of the larger structure.",
            "Consider the sonic quality of the words — how they sound when read aloud.",
            "The imagery should be specific enough to be vivid but universal enough to be relatable.",
            "Use the constraints of the form to create surprising turns of phrase.",
            "The poem should reward rereading with new layers of meaning emerging each time.",
        ],
    }
    options = elaborations.get(category_number, elaborations[1])
    return rng.choice(options)


def seed_test_data(participant_count: int = 50) -> dict[str, Any]:
    """Seed the TEST competition with realistic test data.

    Creates *participant_count* participants, each with a submission containing
    5 responses (one per category). Prompts are ~500 words and unique per
    participant/category combination.
    """
    store = db()
    _ensure_test_competition(store)

    participant_ids: list[str] = []
    batch: list[dict] = []
    for _ in range(participant_count):
        pid = str(uuid.uuid4())
        participant_ids.append(pid)
        batch.append({
            "id": pid,
            "competition_id": TEST_COMPETITION_ID,
            "registration_id": str(uuid.uuid4()),
            "qr_token": f"TEST_{pid.replace('-', '')[:16]}",
            "display_name": f"Test User {pid[:8]}",
            "email": f"test-{pid[:8]}@test.local",
            "status": "SUBMITTED",
        })
        if len(batch) >= 50:
            store.table("pc_participants").insert(batch).execute()
            batch = []
    if batch:
        store.table("pc_participants").insert(batch).execute()

    total_responses = 0
    for pidx, pid in enumerate(participant_ids):
        sub_id = str(uuid.uuid4())
        store.table("pc_submissions").insert({
            "id": sub_id,
            "competition_id": TEST_COMPETITION_ID,
            "participant_id": pid,
            "status": "SUBMITTED",
            "submitted_at": "now()",
        }).execute()

        for cat in CATEGORIES:
            prompts = generate_prompts_for_category(
                category_number=cat["number"],
                category_title=cat["title"],
                category_description=cat["description"],
                count=1,
                target_words=500,
                seed_offset=pidx * 7919,
            )
            prompt_text = prompts[0]
            store.table("pc_responses").insert({
                "submission_id": sub_id,
                "question_id": cat["id"],
                "prompt_text": prompt_text,
                "word_count": len(prompt_text.split()),
                "token_estimate": len(prompt_text) // 4,
            }).execute()
            total_responses += 1

    return {
        "participants": len(participant_ids),
        "submissions": len(participant_ids),
        "responses": total_responses,
    }


def _ensure_test_competition(store) -> None:
    """Ensure the TEST competition and questions exist."""
    store.table("pc_competitions").upsert({
        "id": TEST_COMPETITION_ID,
        "name": "TEST Competition",
        "slug": "test-competition",
        "description": "Isolated competition for evaluation testing.",
        "status": "TEST",
        "leaderboard_visible": False,
        "results_visible": False,
    }).execute()
    rows = [
        {
            "id": cat["id"],
            "competition_id": TEST_COMPETITION_ID,
            "question_number": cat["number"],
            "title": cat["title"],
            "description": cat["description"],
            "input_type": "textarea",
            "max_length": 2000,
            "min_length": 20,
            "display_order": cat["number"],
            "evaluation_config": {},
        }
        for cat in CATEGORIES
    ]
    store.table("pc_questions").upsert(rows).execute()


def cleanup_test_data() -> dict[str, int]:
    """Delete all TEST competition data. Returns counts of deleted rows."""
    store = db()

    subs = (
        store.table("pc_submissions")
        .select("id")
        .eq("competition_id", TEST_COMPETITION_ID)
        .execute()
        .data or []
    )
    sub_ids = [s["id"] for s in subs]

    deleted = {"participants": 0, "submissions": 0, "responses": 0, "jobs": 0, "evaluations": 0}

    if sub_ids:
        resp_rows = (
            store.table("pc_responses")
            .select("id")
            .in_("submission_id", sub_ids)
            .execute()
            .data or []
        )
        resp_ids = [r["id"] for r in resp_rows]

        if resp_ids:
            store.table("pc_evaluations").delete().in_("response_id", resp_ids).execute()
            store.table("pc_evaluation_jobs").delete().in_("response_id", resp_ids).execute()
            deleted["evaluations"] = len(resp_ids)
            deleted["jobs"] = len(resp_ids)

            store.table("pc_responses").delete().in_("id", resp_ids).execute()
            deleted["responses"] = len(resp_ids)

        store.table("pc_submissions").delete().in_("id", sub_ids).execute()
        deleted["submissions"] = len(sub_ids)

    store.table("pc_participants").delete().eq("competition_id", TEST_COMPETITION_ID).execute()
    deleted["participants"] = len(sub_ids)

    return deleted
