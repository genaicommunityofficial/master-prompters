"""Authored test-prompt dataset for seeding the isolated TEST competition.

These prompts are authored offline by the codegen harness (no runtime LLM / API
key required). Each category has a set of rich skeletons containing ``{slot}``
placeholders. The population script expands them with seeded topic/audience/tone
choices so that ``participant_count x 5`` prompts are produced, each unique and
fitted to the live 20–2000 character window.
"""

from __future__ import annotations

import random
from typing import Iterator

# ---------------------------------------------------------------------------
# Category skeletons. Every skeleton is substantial and specific so the final
# prompt reads like a real, considered competition submission.
# ---------------------------------------------------------------------------
SKELETONS: dict[int, list[str]] = {
    1: [
        "Create a meme about {topic} that captures the {emotion} mood of {situation}. "
        "The meme should rely on a {format} template so the setup reads instantly, and the "
        "punchline must land through the contrast between {contrast_a} and {contrast_b}. "
        "Your primary audience is {audience}, who share memes when they feel understood. "
        "The humor should grow out of {relatable_experience}, something nearly everyone has "
        "endured but rarely articulates out loud. Keep the caption short enough for a phone "
        "screen, but layer in a second read that rewards people who scroll back. Consider the "
        "platform: {platform} favors instant recognition, while {platform_b} allows slightly "
        "longer setups. The visual should be instantly recognizable, and the text should "
        "subvert whatever the image implies. Include a reference to {reference} that feels "
        "familiar without being obscure. The tone should be {tone}, never mean-spirited, "
        "because the best memes punch upward, not down. Explain your choice of format and "
        "punchline and how you tested that {audience} would actually share it.",
        "Design a meme that satirizes {topic} in a way that is both {emotion} and a little "
        "uncomfortable because it rings true. Use the {format} template with a setup showing "
        "{setup} and a punchline that reveals {punchline}. Your audience is {audience}, who "
        "communicate in a fast, ironic register and punish anything that feels {tone}. The "
        "joke should come from {relatable_experience}, giving an inside-nod to people who "
        "know {domain}. The caption must be {length} yet complete on its own. Place the "
        "visual in {setting} and make the text interact with the image rather than simply "
        "overlap it. Think about how this lands during {situation} on {platform}. Avoid "
        "punching down at {contrast_a}; instead find the humor in the shared absurdity of "
        "{contrast_b}. Include a subtle {reference} that only regulars on {platform_b} would "
        "catch, strengthening the in-group feeling. Explain the tension between the image and "
        "the caption, and why this particular combination maximizes shareability without "
        "crossing into mean territory.",
     ],
    2: [
        "Generate a detailed prompt for an AI artwork depicting {subject} in a {style} "
        "aesthetic. The composition should feature {composition} and use {lighting} lighting "
        "to build {mood}. Anchor the palette in {colors} with an accent of {accent_color} "
        "that draws the eye to the focal point. Blend {influence_a} and {influence_b} so the "
        "piece feels original rather than derivative, balancing {quality_a} and {quality_b}. "
        "Include fine details like {detail} that reward close inspection, and let the overall "
        "work evoke {emotion} through restraint rather than spectacle. Describe the depth "
        "structure: a clear foreground built on {foreground}, a midground carrying "
        "{midground}, and a background that holds {background} without stealing attention. "
        "Explain how you would direct the lighting to fall across {texture_a} and "
        "{texture_b}, and how the color temperature shifts from shadow to highlight. The "
        "scale of the piece should imply {scale}, and the viewpoint should be {viewpoint}. "
        "Justify each major artistic decision and how it serves the {mood} you are chasing.",
        "Create a prompt for an AI-generated artwork that captures {scene} in a {medium} "
        "medium, folding in elements of {art_movement}. Build depth through "
        "{depth_technique} and use a {perspective} perspective so the viewer is pulled into "
        "the frame. The atmosphere should convey {atmosphere}, and the relationship between "
        "{element} and the surrounding environment should carry the meaning of the piece. "
        "Pay attention to the interaction of {texture_a} and {texture_b}, using contrast to "
        "articulate form. The palette should be led by {colors}, with {accent_color} "
        "reserved for emotional punctuation. Include {detail} as a quiet narrative thread, "
        "and use {lighting} to suggest time of day or emotional temperature. Describe how "
        "the composition guides the eye from {first_glance} to {lasting_impression}, and how "
        "the work changes meaning at different scales. Let the piece reference {reference} "
        "without copying it, and explain the tension between {quality_a} and {quality_b} in "
        "your final rendering. Be explicit about {composition} and how every element earns "
        "its place.",
     ],
    3: [
        "Write a short story about {character}, who discovers {discovery}. Set the narrative "
        "across {setting}, letting each scene tighten tension through {tension_type}. Use a "
        "{narrative_style} voice to explore themes of {theme}, punctuated by moments of "
        "{emotional_beat}. Ground the world in sensory detail—describe how {description_type} "
        "feels, smells, and sounds—so the reader lives inside the moment. Dialogue should "
        "reveal character through what is withheld: {dialogue_technique}. Build toward a "
        "climax that involves {climax_element}, then land a resolution that honors "
        "{resolution_quality}. The structure should move from {opening_image} through rising "
        "complication to a turning point where {character} must choose between "
        "{choice_a} and {choice_b}. Keep the pacing deliberate, accelerating during tension "
        "and slowing for reflection. End with an image, not an explanation, so the theme "
        "resonates rather than being stated. Explain how the setting amplifies the central "
        "conflict and why each turning point was necessary.",
        "Craft a creative piece about {character} navigating {setting} after {catalyst}. "
        "Choose a {narrative_style} register and let the story pivot on {theme}. Use "
        "{tension_type} to keep momentum, but reserve room for {emotional_beat} that reveals "
        "who {character} is becoming. Weave in detailed descriptions of {description_type} "
        "so the world feels inhabited, and let dialogue operate through {dialogue_technique}, "
        "showing subtext rather than stating intent. The inciting incident—{discovery}—should "
        "unsettle the ordinary and force {choice_a} against {choice_b}. Carry the reader to a "
        "climax built on {climax_element} and resolve with {resolution_quality}. Consider the "
        "opening line as a contract with the reader—{opening_image}—and pay it off by the "
        "end. Vary sentence rhythm to mirror emotional temperature, and make the final "
        "paragraph land with restraint. Explain the structural choices and how they serve "
        "the exploration of {theme}.",
     ],
    4: [
        "Create an original song with lyrics and a described musical direction built around "
        "the theme of {topic}. The song should open with {opening_image}, establish a "
        "{genre} groove, and build toward a chorus whose hook is {hook_line}. Structure the "
        "verses around {verse_content}, let the pre-chorus raise the energy through "
        "{build_technique}, and use a bridge that contrasts by {bridge_contrast} before the "
        "final chorus hits harder. The emotional arc should move from {emotion_a} to "
        "{emotion_b}, mirrored in dynamics and instrumentation. Describe the rhythm, the "
        "implied melody shape, and how the vocal sits in a comfortable register. Include "
        "lyrics for at least two verses and a full chorus, and note where you'd add "
        "{instrumentation} to thicken the texture. Explain how repetition creates a hook "
        "without becoming monotonous, and how the song would translate to {setting}.",
        "Write an original song combining lyrics and production notes that explore {topic} "
        "through {emotion_a} to {emotion_b}. Establish a {genre} foundation, then use "
        "{hook_line} as the central refrain that anchors the song. Order the sections so the "
        "verses deliver {verse_content}, the pre-chorus lifts through {build_technique}, and "
        "the bridge gives {bridge_contrast} before a final chorus that lands differently "
        "because of that contrast. Provide complete lyrics for the verses, a chorus, and a "
        "bridge. Describe the melodic contour, the bass and drum pocket, and where "
        "{instrumentation} enters. Think about how the song feels in {setting} and justify "
        "production choices that serve the emotional narrative rather than decoration.",
     ],
    5: [
        "Write poetry in {language} that explores {theme}. Build the poem using {form}, and "
        "let {imagery} carry the emotional weight. Each line should work alone yet gather "
        "force within the whole, and the music of the words—how {vowels} and consonants "
        "interact—should matter as much as their meaning. Center the poem on {subject}, "
        "moving from {opening_image} toward a turn that reframes {theme}. Use "
        "{device} to create surprising connections, and honor {tradition} while keeping the "
        "voice unmistakably contemporary. The poem should read aloud beautifully in "
        "{language}, reward a second reading with new layers, and end on an image that "
        "resonates without concluding. Include a brief note on how the formal choices "
        "support the emotional core.",
        "Craft a poem in {language} that holds {theme} and {theme_b} in tension. Choose "
        "{form} as your container, using {imagery} to ground abstract feeling in the "
        "sensory. attend closely to the sonic texture—{vowels}, rhythm, and repetition—so "
        "the poem moves with intention when spoken. Develop {subject} from {opening_image} "
        "to a turn that lets the reader see it anew, deploying {device} to make the familiar "
        "strange. Root the work in {tradition}, but let it speak in a fresh register. The "
        "poem should deepen on rereading, unify its images, and close on {closing_image} "
        "without wrapping the meaning in a bow. Add a short commentary explaining how form "
        "and sound support the poem's theme.",
     ],
}

# ---------------------------------------------------------------------------
# Closing "craft note" appended to every prompt so it comfortably clears the
# target word count with genuine, category-specific substance rather than
# filler. Each is a detailed justification of craft choices.
# ---------------------------------------------------------------------------
CRAFT_NOTES: dict[int, list[str]] = {
    1: [
        "In closing, explain your full creative process: why this meme format, how you "
        "arrived at the punchline, and how you would test it on your target audience to "
        "confirm it lands. Describe the exact relationship between the image and the caption, "
        "and how either one alone would fail to be funny. Lay out at least two alternative "
        "versions you considered and why you rejected each, then justify the final choice with "
        "reference to timing, tone, and platform norms. Finally, consider a potential "
        "misreading of the joke, explain what could go wrong, and how you would tighten the "
        "wording to keep it both sharp and good-natured.",
    ],
    2: [
        "Finally, write a short artist's statement defending your choices. Explain how the "
        "composition, palette, and lighting each serve the intended mood and why no element is "
        "decorative. Describe how the piece guides a viewer from first glance to a slower, "
        "more detailed reading, and how the recurring motif threads the composition together. "
        "Discuss the balance between fidelity to your influences and originality, noting where "
        "you depart from convention and what that departure buys. Conclude with how the work "
        "would change at a different scale or medium, and what you would refine if given more "
        "time.",
    ],
    3: [
        "Close by reflecting on the story's craft. Explain how your opening image sets a "
        "promise the reader trusts, and how each middle scene earns the climax. Discuss the "
        "role of the setting as an active force in the conflict rather than a backdrop, and how "
        "the pacing accelerates and relaxes to control tension. Explain what the dialogue "
        "reveals indirectly and why you withheld certain information. Finally, justify the "
        "ending you chose, why it is the most honest resolution available, and what single "
        "image you hope lingers with the reader.",
    ],
    4: [
        "Finish with production notes. Explain how the melody's contour maps onto the emotional "
        "arc of the lyric, and how the dynamics build from a sparse opening to a fuller chorus. "
        "Describe the arrangement choices—which instruments enter when and why—so each addition "
        "earns its place. Discuss how the song would translate to a live setting and a studio "
        "recording, and reconcile the two. Finally, defend the hook's repetition as a "
        "structural strength rather than a shortcut, and note what you would refine before "
        "finalizing.",
    ],
    5: [
        "Conclude with a brief craft note. Explain how the chosen form shapes the reading of "
        "the poem and where you rhyme, enjamb, or break lines to create tension and release. "
        "Discuss the sound of the poem in {language}—how vowels, rhythm, and repetition build "
        "its music—and what you were trying to achieve on the page versus aloud. Describe the "
        "image that anchors the poem and how it transforms across the stanzas. Finally, "
        "reflect on what the poem leaves open and why the ending resists neat closure.",
    ],
}

# ---------------------------------------------------------------------------
# Category-specific elaboration pools used to reach the target word count while
# keeping each prompt substantive rather than padded with filler.
# ---------------------------------------------------------------------------
ELABORATIONS: dict[int, list[str]] = {
    1: [
        "Consider the timing and cultural context so the humor lands in the right week, not a stale one.",
        "The caption should fit a phone screen but offer a second layer for anyone who scrolls back.",
        "Think about how the meme performs across {platform} and {platform_b}, where the norms differ.",
        "Balance broad relatability with a sharper in-group reference to reward loyal followers.",
        "Describe exactly how the image and text connect, so the joke depends on both working together.",
        "Weigh the risk of the joke being misread and how to keep the delivery precise enough to avoid it.",
    ],
    2: [
        "Explain the interplay of light and shadow so the depth reads clearly at any viewing size.",
        "Consider how the piece changes when printed large versus viewed on a small screen.",
        "Describe how the color relationships create harmony while preserving dynamic tension.",
        "Walk through how the composition leads the eye and where it holds attention longest.",
        "Include deliberate details that reward extended viewing without cluttering the main subject.",
    ],
    3: [
        "Let each scene advance both plot and character so nothing feels like filler.",
        "Use sensory specifics to anchor the reader in the physical reality of the scene.",
        "Shape dialogue so that what characters leave unsaid matters as much as what they say.",
        "Control pace deliberately—quicken through tension, slow down for reflection.",
        "Make the ending feel surprising yet inevitable once the reader looks back.",
    ],
    4: [
        "Describe how the implied melody and rhythm support the emotional arc of the lyrics.",
        "Consider how the song sounds live versus in a polished studio recording.",
        "Use repetition as a structural hook without letting it become monotonous.",
        "Explain how the bridge creates contrast that makes the final chorus more powerful.",
        "Keep the melody within a comfortable vocal range so it is singable and memorable.",
    ],
    5: [
        "Let each line work independently while gathering force within the stanza structure.",
        "Consider how the words sound aloud, letting the sonic texture serve the meaning.",
        "Choose imagery specific enough to be vivid yet universal enough to move any reader.",
        "Use the constraints of the form to produce surprising and precise turns of phrase.",
        "Let the poem reward a second reading by layering meaning beneath the surface.",
    ],
}

# ---------------------------------------------------------------------------
# Slot values (shared, varied) used to expand skeletons into unique prompts.
# ---------------------------------------------------------------------------
FILL_INS: dict[str, list[str]] = {
    "topic": [
        "working from home", "campus life", "online exams", "group projects",
        "commuting in rush hour", "group chats that blow up", "deadlines",
        "forgetting why you walked into a room", "the eternal Wi-Fi struggle",
        "meal planning chaos", "morning routines", "the annual festival crowd",
        "student discount culture", "all-nighters before submissions",
        "the gym in January", "college canteen queues", "autocorrect betrayals",
        "the unread-message pile", "public transport weather", "exam week",
    ],
    "emotion": ["joyful", "exasperated", "smug", "nostalgic", "triumphant", "dreadful", "relieved", "sarcastic"],
    "situation": [
        "a chaotic weekday morning", "the last five minutes of a deadline",
        "a packed lecture hall", "a surprise pop quiz", "a family video call",
        "an era of remote learning", "the day before a holiday", "a group-call meltdown",
    ],
    "format": ["single-panel static", "two-panel before-after", "three-panel sequence", "reaction-style", "classic top-and-bottom"],
    "contrast_a": [
        "what people expect", "the polished version", "the official announcement",
        "the poster image", "the teacher's plan", "the perfect study schedule",
    ],
    "contrast_b": [
        "what actually happens", "the messy reality", "the behind-the-scenes truth",
        "the lived experience", "the actual execution", "the chaotic outcome",
    ],
    "audience": [
        "university students", "young professionals", "college freshers",
        "remote workers", "commuters", "final-year students", "gamers", "social-media regulars",
    ],
    "relatable_experience": [
        "procrastinating until panic", "staying up late to finish work",
        "saying yes to too many things", "misreading a deadline by a day",
        "the group project carried by one person", "assuming you have more time than you do",
    ],
    "platform": ["Instagram Reels", "X", "TikTok", "Facebook", "WhatsApp status"],
    "platform_b": ["LinkedIn", "Reddit", "Discord", "YouTube", "Telegram channels"],
    "reference": [
        "a well-known meme", "a classic movie scene", "an office inside joke",
        "a famous dialogue", "a shared campus landmark", "a trending audio clip",
    ],
    "tone": ["wry", "affectionate", "deadpan", "playful", "observational", "cheeky"],
    "setup": [
        "a normal expectation", "an innocent first frame", "a reasonable plan",
        "a polite beginning", "an ideal setup", "a confident opening",
    ],
    "punchline": [
        "the joke's twist", "the unexpected outcome", "the ironic reveal",
        "the painful truth", "the subverted ending", "the punchline that stings and comforts",
    ],
    "domain": [
        "coding culture", "academic life", "gaming", "cricket", "pop music",
        "startup culture", "cooking fails", "public transport",
    ],
    "length": ["under ten words", "exactly seven words", "short and sharp", "minimal"],
    "setting": [
        "a dorm room", "a campus courtyard", "a crowded train", "a virtual meeting",
        "a lecture hall", "a late-night study cafe", "a hostel corridor",
    ],
    # art
    "subject": [
        "a lone figure walking through a monochrome city", "a surreal garden at dusk",
        "an abandoned observatory", "a marketplace frozen in time", "a storm over a valley",
        "a library that defies physics", "a lone tree on a cliff", "a dancer mid-leap in fog",
    ],
    "style": ["neo-noir", "impressionist", "cyberpunk", "baroque", "minimalist", "surrealist", "vaporwave", "gothic"],
    "composition": [
        "a strong central subject with layered depth", "a rule-of-thirds arrangement",
        "a diagonal sweep leading to a focal point", "a symmetrical frame with quiet asymmetry",
        "a close-up anchored by negative space", "a wide establishing vista",
    ],
    "lighting": ["golden-hour rim light", "harsh directional", "soft diffused", "low-key dramatic", "neon-split", "candlelit"],
    "mood": [
        "quiet melancholy", "anticipation", "serene awe", "uneasy stillness",
        "wistful nostalgia", "wonder", "brooding tension", "tender calm",
    ],
    "colors": [
        "deep teals and slate", "warm ochres and rust", "muted pastels", "cobalt and amber",
        "monochrome with one accent", "autumnal oranges and plum", "cool grays and crisp white",
    ],
    "accent_color": ["a single crimson note", "electric gold", "a soft rose highlight", "one streak of cyan", "vermilion"],
    "influence_a": [
        "classical academic painting", "early 20th-century illustration",
        "1970s sci-fi covers", "Japanese woodblock prints", "the Dutch masters", "Art Deco posters",
    ],
    "influence_b": [
        "modern editorial photography", "mid-century minimalism",
        "contemporary digital painting", "street photography", "abstract expressionism",
    ],
    "quality_a": ["painterly looseness", "graphic clarity", "emotional weight", "technical precision", "playful energy"],
    "quality_b": ["editorial tidiness", "atmospheric depth", "formal restraint", "loose spontaneity", "quiet stillness"],
    "detail": [
        "a faint watermark of light", "a tiny recurring motif", "scattered fallen petals",
        "a distant window glowing", "subtle film grain", "an almost-hidden shadow figure",
    ],
    "foreground": ["bold shapes that anchor the frame", "a crisp silhouette", "close foreground texture", "a leading line"],
    "midground": ["the narrative action", "the emotional focal plane", "flowing forms", "the subject's world"],
    "background": ["a receding horizon", "soft atmospheric haze", "a suggested structure", "open negative space"],
    "texture_a": ["rough stone", "soft fabric", "polished glass", "aged paper", "wet metal", "fresh foliage"],
    "texture_b": ["smooth ceramic", "weathered wood", "thin mist", "worn leather", "crisp linen", "cold marble"],
    "scale": [
        "an intimate, hand-held closeness", "a monumental, architectural presence",
        "a human-scaled warmth", "a vast, humbling sweep",
    ],
    "viewpoint": ["eye-level", "a dramatic low angle", "a birds-eye overview", "a close over-the-shoulder"],
    "scene": [
        "a rain-slicked street at night", "a sunlit meadow at the edge of a forest",
        "a quiet railway station", "a rooftop overlooking a city", "a cave opening onto an ocean",
        "a winter market in the evening", "a field of sunflowers at golden hour",
    ],
    "medium": ["oil-inspired", "watercolor-inspired", "charcoal and ink", "digital matte", "etched line", "gouache"],
    "art_movement": [
        "impressionism", "surrealism", "abstract expressionism", "romanticism",
        "precisionism", "the Vienna Secession", "naive art",
    ],
    "depth_technique": [
        "atmospheric perspective", "overlapping planes", "scale gradation",
        "careful value separation", "directional light falloff",
    ],
    "perspective": ["one-point", "two-point", "isometric", "aerial", "low-lying worm's-eye"],
    "atmosphere": [
        "a humid stillness", "brisk clarity", "a dreamlike haze", "charged anticipation",
        "gentle melancholy", "a celebratory warmth",
    ],
    "element": [
        "water", "wind", "a single figure", "an open doorway", "reflections", "shadows",
    ],
    "first_glance": ["the dominant shape", "the boldest color", "the central figure", "the primary light"],
    "lasting_impression": ["the quiet detail", "the unresolved edge", "the implied movement", "the lingering shadow"],
    # story
    "character": [
        "a meticulous librarian", "a restless engineering student", "an elderly watchmaker",
        "a shy music teacher", "a night-shift baker", "a retired seafarer",
        "a curious child", "a burnt-out writer", "a first-generation graduate",
    ],
    "discovery": [
        "an old letter hidden in a book", "a hidden passage in the basement",
        "a forgotten family photograph", "a message inside a repaired clock",
        "a diary left on a train", "a door that was never supposed to open",
    ],
    "setting": [
        "a coastal town in winter", "a crowded city apartment", "a remote mountain village",
        "a university campus at night", "a small railway station", "an old family home",
        "a sun-scorched plains town", "a misty riverside neighborhood",
    ],
    "tension_type": [
        "unspoken family friction", "a ticking deadline", "gathering dread",
        "a quiet rivalry", "approaching conflict", "an unresolved mystery",
    ],
    "narrative_style": [
        "first-person confessional", "tight third-person", "an epistolary structure",
        "unreliable narration", "a lyrical, image-driven voice", "a direct and spare style",
    ],
    "theme": [
        "belonging and displacement", "the cost of ambition", "memory and identity",
        "loss and renewal", "duty versus desire", "the search for home",
    ],
    "emotional_beat": [
        "a moment of unexpected tenderness", "a hollow realization", "a small act of courage",
        "a flicker of hope", "a quiet goodbye", "a sudden, earned laugh",
    ],
    "description_type": [
        "the smell of salt and rain", "the texture of old wood", "the sound of distant traffic",
        "the bite of cold air", "the weight of a heavy silence", "the warmth of shared light",
    ],
    "dialogue_technique": [
        "subtext that hides the real conflict", "silences that say more than words",
        "interrupted sentences", "repeated phrases that shift meaning", "contradictory small talk",
    ],
    "climax_element": [
        "a confrontation that was years coming", "a confession made too late",
        "a choice under pressure", "an arrival that changes everything", "a truth finally spoken",
    ],
    "resolution_quality": [
        "a measured, earned quiet", "an open but hopeful frame", "a return to the ordinary",
        "a reconciliation that does not forgive everything", "an image that lingers",
    ],
    "opening_image": [
        "rain on a window at dusk", "a suitcase half-packed", "a single lit lamp",
        "a train pulling away", "an empty chair at a full table", "a door left ajar",
    ],
    "choice_a": ["security", "the familiar path", "what is expected", "comfort", "the safe answer"],
    "choice_b": ["risk", "the unknown road", "what is honest", "discomfort", "the true answer"],
    "catalyst": [
        "a sudden job loss", "an unexpected inheritance", "a letter from an old friend",
        "a health scare", "a stranger arriving in town", "a canceled plan",
    ],
    # song
    "genre": ["indie pop", "lo-fi R&B", "acoustic folk", "synth-wave", "alt-rock", "trap-inspired", "neo-soul", "dream pop"],
    "hook_line": [
        "a two-word repeated phrase", "an earworm melodic hook", "a chantable one-liner",
        "a rising refuse-style hook", "a shouted anthem line",
    ],
    "opening_image": [
        "a single piano note over silence", "a distant train horn", "the scratch of a needle",
        "a breath before the beat drops", "a humming melody under fuzz",
    ],
    "verse_content": [
        "a memory rendered in plain detail", "a mounting list of small losses",
        "a setup that pays off in the chorus", "story-like scenes in present tense",
        "a confession delivered quietly",
    ],
    "build_technique": [
        "layered backing vocals", "a rising synth pad", "an added percussion layer",
        "a key change", "a lifted register", "a tightened groove",
    ],
    "bridge_contrast": [
        "a stripped-down, vulnerable section", "an instrumental break", "a sudden tempo drop",
        "a key change into a higher register", "a spoken-word interlude",
    ],
    "emotion_a": ["restless", "wistful", "uncertain", "yearning", "worn"],
    "emotion_b": ["hopeful", "resolved", "defiant", "peaceful", "triumphant"],
    "instrumentation": [
        "a soft piano line", "a driving bass", "warm analog synths", "layered guitars",
        "a string section", "subtle percussion", "a saxophone counter-melody",
    ],
    "setting": [
        "a late-night drive", "a bedroom studio", "a packed festival stage",
        "a quiet living room session", "a sunny road trip", "a rainy city street",
    ],
    # poetry
    "language": [
        "Hindi", "Tamil", "Bengali", "Telugu", "Marathi", "Malayalam", "Kannada",
        "Gujarati", "Punjabi", "Urdu", "Odia", "Assamese", "English",
    ],
    "form": [
        "a free-verse meditation", "a sonnet-like structure", "a series of haiku",
        "a ghazal", "repetition-driven free verse", "a villanelle", "prose poem sections",
    ],
    "imagery": [
        "monsoon rain and wet earth", "candlelight and shadow", "seasonal change",
        "the sea and its edge", "a monsoon-swept street", "dusk over rooftops",
        "the smell of old books", "a train window at dawn",
    ],
    "vowels": [
        "open long vowels", "clipped stops and plosives", "soft sibilants",
        "nasal music", "round back vowels", "sharp bright vowels",
    ],
    "subject": [
        "a parent's quiet sacrifice", "flight and return", "the small rituals of home",
        "a language on the verge of being lost", "the distance between generations",
        "an ordinary day made extraordinary", "home as a place and a memory",
    ],
    "device": [
        "metaphor and personification", "anaphora and refrain", "careful enjambment",
        "ironic juxtaposition", "extended metaphor", "a recurring motif",
    ],
    "tradition": [
        "the classical bhakti lyric", "oral folk tradition", "modernist experimentation",
        "the confessional lyric", "regional narrative poetry", "the ghazal's formal rules",
    ],
    "theme_b": ["time", "loss", "memory", "longing", "renewal", "identity"],
    "closing_image": [
        "an extinguished lamp", "a wave pulling back", "a door closing softly",
        "the first star of evening", "an empty chair in sunlight", "a seed in cupped hands",
    ],
}


PROMPT_MIN_CHARS = 20
PROMPT_MAX_CHARS = 2000


def fit_prompt_char_limit(
    text: str,
    min_len: int = PROMPT_MIN_CHARS,
    max_len: int = PROMPT_MAX_CHARS,
) -> str:
    """Trim to the live competition character window without dropping below min_len when possible."""
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_len:
        return cleaned
    cut = cleaned[:max_len].rsplit(" ", 1)[0]
    if len(cut) >= min_len:
        return cut
    return cleaned[:max_len]


def dataset_prompts_for_category(
    category_number: int,
    count: int,
    target_words: int = 80,
    seed_offset: int = 0,
) -> list[str]:
    """Expand authored skeletons into *count* unique prompts, then fit 20–2000 characters.

    Combinatorial variety comes from (participant, count, category)-seeded
    selection of skeleton + fill-ins + elaborations.
    """
    skeletons = SKELETONS.get(category_number, SKELETONS[1])
    elaborations = ELABORATIONS.get(category_number, ELABORATIONS[1])
    craft_notes = CRAFT_NOTES.get(category_number, CRAFT_NOTES[1])
    rng = random.Random(category_number * 1000003 + count * 7919 + seed_offset)

    prompts: list[str] = []
    for i in range(count):
        skeleton = skeletons[(i + rng.randrange(len(skeletons))) % len(skeletons)]
        filled = skeleton
        for var in list(FILL_INS.keys()):
            placeholder = "{" + var + "}"
            if placeholder in filled:
                filled = filled.replace(placeholder, rng.choice(FILL_INS[var]))

        # Attach a substantive closing craft note before padding to length.
        craft_note = craft_notes[0]
        for var in list(FILL_INS.keys()):
            placeholder = "{" + var + "}"
            if placeholder in craft_note:
                craft_note = craft_note.replace(placeholder, rng.choice(FILL_INS[var]))
        filled += " " + craft_note

        current_words = len(filled.split())
        pad_rounds = 0
        while current_words < target_words and pad_rounds < 30:
            elaboration = rng.choice(elaborations)
            for var in list(FILL_INS.keys()):
                placeholder = "{" + var + "}"
                if placeholder in elaboration:
                    elaboration = elaboration.replace(
                        placeholder, rng.choice(FILL_INS[var])
                    )
            filled += " " + elaboration
            current_words = len(filled.split())
            pad_rounds += 1

        words = filled.split()
        if len(words) > int(target_words * 1.15):
            words = words[: int(target_words * 1.15)]
        prompts.append(fit_prompt_char_limit(" ".join(words)))
    return prompts


def iter_participant_prompts(
    participant_count: int,
    categories: list[dict],
    target_words: int = 80,
) -> Iterator[list[str]]:
    """Yield one list of 5 category prompts per participant."""
    for pidx in range(participant_count):
        yield [
            dataset_prompts_for_category(
                cat["number"],
                count=1,
                target_words=target_words,
                seed_offset=pidx * 7919 + cat["number"] * 13,
            )[0]
            for cat in categories
        ]
