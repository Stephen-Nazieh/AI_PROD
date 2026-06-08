---
name: DeParadigm Media Studio Launch Playbook
description: orchestration
metadata:
  paperclip:
    tags:
    - orchestration
    source_file: 01_SKILLS/studio_launch_playbook.md
    format_detected: yaml_frontmatter
    original_agent_id: studio_producer
    model_target: qwen3-coder-32b-mlx
---

# DeParadigm Media Studio Launch Playbook

Phased development methodology governing how scriptwriter and asset generator agents validate curriculum data before initiating FCPXML compilation lines. Adapted from NEXUS multi-phase pipeline architecture for the DeParadigm Media local content factory.

---

## Phase 0 — Intelligence & Discovery (3-7 days)

> **Agents**: Research Scout, Vault Librarian | **Gate Keeper**: Studio Producer

### Objective
Validate curriculum data and topic viability before committing scriptwriting resources. No scripts until the topic, wiki coverage, and competitive landscape are understood.

### Pre-Conditions
- [ ] Topic brief or content concept exists
- [ ] Target channel identified (Dev & Cloud / AP Stats / Translation / Deep Focus)
- [ ] Target audience avatar confirmed

### Agent Activation Sequence

#### Wave 1: Parallel Launch (Day 1)

**Research Scout — Curriculum Intelligence Lead**
```
Activate Research Scout for curriculum intelligence on [TOPIC].

Deliverables required:
1. Competitive landscape analysis (existing videos on this topic)
2. Curriculum gap mapping: what AP Stats / GCP concepts are underserved?
3. Trend lifecycle: where is this topic in the adoption curve?
4. 3-6 month content forecast with confidence intervals
5. Source verification: minimum 5 unique, verified academic or technical sources

Output: Strategic Research Brief saved to 03_ASSETS/_HANDOFF_FCP_CAPCUT/projects/
Timeline: 2 days
```

**Vault Librarian — Wiki Coverage Analysis**
```
Activate Vault Librarian for compiled_wiki/ coverage audit on [TOPIC].

Deliverables required:
1. Existing wiki nodes on related topics
2. Content overlap / redundancy analysis
3. Missing sub-topics that should be covered
4. Wikilink connectivity gaps
5. Raw source material availability in 02_CURRICULUM/raw_sources/

Output: Wiki Coverage Report saved to 02_CURRICULUM/compiled_wiki/
Timeline: 1 day
```

### Quality Gate Checklist

| # | Criterion | Evidence Source | Status |
|---|-----------|----------------|--------|
| 1 | Topic opportunity validated with audience fit | Research Scout brief | ☐ |
| 2 | ≥3 curriculum gaps identified with supporting data | Vault Librarian report | ☐ |
| 3 | No blocking contradictions in existing wiki | Vault Librarian audit | ☐ |
| 4 | Raw source material available or acquirable | Vault Librarian inventory | ☐ |
| 5 | Research brief delivered with GO/NO-GO recommendation | Studio Producer | ☐ |

### Gate Decision
- **GO**: Proceed to Phase 1 — Script & Strategy
- **NO-GO**: Archive findings, redirect resources
- **PIVOT**: Modify topic/angle based on findings, re-run targeted discovery

---

## Phase 1 — Script & Strategy (5-10 days)

> **Agents**: Script Architect, Visual Director, SEO Architect | **Gate Keepers**: Studio Producer + Script Architect

### Objective
Define what the video covers, how it's structured, and what success looks like — before generating a single FCPXML line.

### Pre-Conditions
- [ ] Phase 0 Quality Gate passed (GO decision)
- [ ] Research Brief and Wiki Coverage Report received
- [ ] Channel alignment confirmed

### Agent Activation Sequence

#### Step 1: Strategic Framing (Day 1-3, Parallel)

**Script Architect — Narrative & Voice Design**
```
Activate Script Architect for script development on [TOPIC].

Input: Phase 0 Research Brief + Wiki Coverage Report
Deliverables required:
1. Full production-ready script with [CHAPTER] markers
2. [B-ROLL CUE] tags for Visual Director
3. [BUILDER MOMENT] identification for Dev & Cloud content
4. Word count target aligned to video length (150 words/min)
5. Brand voice compliance check

Output: Script markdown saved to 03_ASSETS/_HANDOFF_FCP_CAPCUT/projects/
Timeline: 3 days
```

**Visual Director — Shot & Graphics Planning**
```
Activate Visual Director for visual production brief on [TOPIC].

Input: Completed Script with [B-ROLL CUE] tags
Deliverables required:
1. Scene-by-scene shot breakdown
2. B-roll shot list (screen recordings, animations, VTuber moments)
3. Graphics package brief (lower thirds, chapter titles, stats overlays)
4. Color grading direction per channel aesthetic
5. Music & audio direction

Output: Visual Brief saved to 03_ASSETS/_HANDOFF_FCP_CAPCUT/projects/
Timeline: 2 days
```

**SEO Architect — Discovery & Metadata Package**
```
Activate SEO Architect for metadata package on [TOPIC].

Input: Completed Script + Research Brief
Deliverables required:
1. 5 title options with Five Title Tests applied
2. Recommended title with justification
3. Full description (up to 5,000 characters)
4. Chapter markers from [CHAPTER] tags
5. 20-30 tags (broad + specific + brand + long-tail)
6. Thumbnail text brief (2-4 words)
7. Shorts clip recommendation

Output: SEO Package saved to 03_ASSETS/_HANDOFF_FCP_CAPCUT/projects/
Timeline: 1 day
```

### Quality Gate Checklist

| # | Criterion | Evidence Source | Status |
|---|-----------|----------------|--------|
| 1 | Script covers 100% of curriculum gaps identified in Phase 0 | Cross-reference with Wiki Coverage Report | ☐ |
| 2 | Visual brief complete with shot list and graphics package | Visual Director deliverable | ☐ |
| 3 | SEO package with validated title and description | SEO Architect deliverable | ☐ |
| 4 | Script passes brand voice check (Sacred Words, scout frame) | Script Architect self-check | ☐ |
| 5 | All deliverables saved to HANDOFF_FCP_CAPCUT/projects/ | File system verification | ☐ |

### Gate Decision
- **APPROVED**: Proceed to Phase 2 with full Script + Visual + SEO Package
- **REVISE**: Specific items need rework
- **RESTRUCTURE**: Fundamental narrative issues (return to Phase 0)

---

## Phase 2 — Asset Generation & Pre-Production (3-5 days)

> **Agents**: Media Bridge, Motion Template, Audio Pipeline | **Gate Keeper**: Studio Producer

### Objective
Build the technical and asset foundation that all subsequent FCPXML compilation depends on. Get the assets ready before timeline assembly.

### Pre-Conditions
- [ ] Phase 1 Quality Gate passed (Script + Visual + SEO Package approved)
- [ ] All Phase 1 deliverables received
- [ ] Channel-specific aesthetic confirmed

### Agent Activation Sequence

#### Workstream A: Asset Preparation (Day 1-3, Parallel)

**Media Bridge — FCPXML Scaffold Generation**
```
Activate Media Bridge for FCPXML scaffold on [PROJECT].

Input: Visual Director brief + Script chapter markers
Deliverables required:
1. Base FCPXML v1.11 scaffold with sequence structure
2. Resource mappings (format, motion templates, audio roles)
3. Spine placeholder for chapter segments
4. Project naming per output convention

Output: .fcpxml scaffold saved to 03_ASSETS/_HANDOFF_FCP_CAPCUT/projects/
Timeline: 1 day
```

**Motion Template — Graphics Asset Rendering**
```
Activate Motion Template for graphics generation on [PROJECT].

Input: Visual Director Graphics Package Brief
Deliverables required:
1. Lower third templates (key stats, tool names)
2. Chapter title cards per channel aesthetic
3. Stats overlay graphics (for AP Stats data visualizations)
4. Terminal command overlay templates (for Dev & Cloud)

Output: Rendered .motn files to 03_ASSETS/_HANDOFF_FCP_CAPCUT/visuals/
Timeline: 2 days
```

**Audio Pipeline — Voice & Music Preparation**
```
Activate Audio Pipeline for audio asset preparation on [PROJECT].

Input: Completed Script
Deliverables required:
1. Voice track recording or XTTS v2 generation
2. Logic Pro mastering pass (highpass 80Hz, lowpass 15kHz, loudnorm -16 LUFS)
3. BGM selection per channel mood
4. Sound effect library for key moments

Output: Mastered audio to 03_ASSETS/_HANDOFF_FCP_CAPCUT/audio/
Timeline: 2 days
```

### Verification Checkpoint (Day 4-5)

**Studio Producer Verification**
```
Verify the following:
1. FCPXML scaffold validates against Apple FCPXML v1.11 spec
2. All motion template assets render without error
3. Audio tracks pass loudness normalization (-14 LUFS target)
4. Asset naming convention followed consistently
5. All files saved to correct HANDOFF_FCP_CAPCUT/ subdirectories

Verdict: PASS / FAIL with specific issues
```

### Quality Gate Checklist

| # | Criterion | Evidence Source | Status |
|---|-----------|----------------|--------|
| 1 | FCPXML scaffold validates | Python validation script | ☐ |
| 2 | Motion templates render correctly | Visual inspection | ☐ |
| 3 | Audio passes loudness spec | ffmpeg loudnorm analysis | ☐ |
| 4 | All assets follow naming convention | File system audit | ☐ |
| 5 | Asset directory structure correct | Directory tree check | ☐ |

### Gate Decision
- **PASS**: Working asset foundation → Phase 3 activation
- **FAIL**: Specific asset issues → Fix and re-verify

---

## Phase 3 — Build & Iterate (2-12 days)

> **Agents**: Script Agent, Editor Brief, Thumbnail Designer | **Gate Keeper**: Studio Producer

### Objective
Implement all post-production through continuous Script→Edit→Review loops. Every segment is validated before the next begins.

### The Script→Edit→Review Loop

```
FOR EACH chapter IN script_backlog (ordered by sequence):

  1. Script Agent provides chapter-specific dialogue cues
  2. Editor Brief Agent assembles segment with B-roll + graphics + audio
  3. Studio Producer REVIEWS segment
     - Visual verification (screenshot evidence)
     - Audio quality check (no clipping, balanced mix)
     - Brand consistency check (colors, typography, pacing)
  4. IF verdict == PASS:
       Mark segment complete
       Inject into FCPXML spine
       Move to next chapter
     ELIF verdict == FAIL AND attempts < 3:
       Send edit notes to Editor Brief Agent
       Editor fixes specific issues
       Return to step 3
     ELIF attempts >= 3:
       ESCALATE to Studio Producer
       Options: reassign, decompose, defer, or accept
  5. UPDATE production status report
```

### Parallel Build Tracks

**Track A: Core Video Assembly**
- Managed by: Studio Producer
- Agents: Script Agent, Editor Brief Agent, Visual Director
- QA: Studio Producer (visual + audio verification)
- Sprint cadence: Chapter-by-chapter assembly

**Track B: Thumbnail & Packaging**
- Managed by: Thumbnail Designer
- Agents: Thumbnail Designer, SEO Architect
- Activities: Thumbnail concepts, A/B test recommendation, final packaging

**Track C: Multi-Platform Adaptation**
- Managed by: Short Video Coach
- Agents: Short Video Coach, Bilibili Strategist, Xiaohongshu Specialist
- Activities: Shorts extraction, vertical crop, platform-specific exports

### Quality Gate Checklist

| # | Criterion | Evidence Source | Status |
|---|-----------|----------------|--------|
| 1 | All script chapters assembled into FCPXML | File verification | ☐ |
| 2 | All audio tracks synced and balanced | Audio analysis | ☐ |
| 3 | All graphics overlays placed correctly | Screenshot evidence | ☐ |
| 4 | Thumbnail creative brief complete | Thumbnail Designer output | ☐ |
| 5 | Multi-platform exports prepared | File system check | ☐ |
| 6 | Final runtime within target (+/- 10%) | Duration check | ☐ |

### Gate Decision
- **PASS**: Feature-complete video → Phase 4 activation
- **CONTINUE**: More chapters needed → Continue Phase 3
- **ESCALATE**: Systemic issues → Studio Producer intervention

---

## Phase 4 — Quality & Hardening (3-7 days)

> **Agents**: Studio Producer, Short Video Coach | **Gate Keeper**: Studio Producer (sole authority)

### Objective
The final quality gauntlet. Studio Producer defaults to "NEEDS WORK" — proof of production readiness required with evidence.

### Critical Mindset

> **The Studio Producer's default verdict is NEEDS WORK.**
>
> Production readiness requires:
> - Complete video from hook to sign-off
> - Cross-platform consistency (horizontal 16:9, vertical 9:16)
> - Audio quality under load (no clipping, balanced mix)
> - FCPXML validity (passes schema validation)
> - Brand compliance (colors, Sacred Words, scout frame)
>
> A B/B+ rating on first pass is normal and expected.

### Agent Activation Sequence

#### Step 1: Evidence Collection (Day 1-2)

**Studio Producer — Comprehensive Review**
```
Activate Studio Producer for final quality review on [PROJECT].

Verification required:
1. Full video playback (no black frames, no audio desync)
2. Thumbnail frame quality check
3. FCPXML schema validation
4. Multi-platform export verification (horizontal + vertical)
5. Subtitle accuracy check (technical terms, math notation)
6. Brand compliance audit (Sacred Words, color palette, tone)

Format: Quality Certification Report
Verdict: READY / NEEDS WORK / NOT READY
Timeline: 2 days
```

#### Step 2: Fix Cycle (Day 3-5, if NEEDED)

Issues enter the Script→Edit→Review loop (Phase 3 mechanics).
Each fix must pass Studio Producer verification.

#### Step 3: Final Judgment (Day 5-7)

**Studio Producer — THE FINAL VERDICT**

```
MANDATORY PROCESS:

Step 1: Content Verification
- Watch complete video end-to-end
- Verify all [CHAPTER] markers present
- Check all [B-ROLL CUE] fulfilled
- Confirm [BUILDER MOMENT] quality (if applicable)

Step 2: Technical Verification
- FCPXML validates against v1.11 schema
- Audio peaks below -1dBFS
- Loudness at -14 LUFS (+/- 1)
- Exports at correct resolution and frame rate

Step 3: Brand Verification
- Sacred Words used naturally
- Scout frame visible throughout
- Color palette matches channel aesthetic
- Sign-off closes every video: "Stay hungry. Keep building."

VERDICT OPTIONS:
- READY: Production-ready video (rare first pass)
- NEEDS WORK: Specific issues with fix list (expected)
- NOT READY: Major structural issues requiring Phase 1 revisit
```

### Quality Gate — THE FINAL GATE

| # | Criterion | Threshold | Evidence Required |
|---|-----------|-----------|-------------------|
| 1 | Complete video from hook to sign-off | All chapters assembled | Full playback |
| 2 | Cross-platform exports valid | Horizontal + vertical | File verification |
| 3 | Audio quality certified | No clipping, -14 LUFS | ffmpeg analysis |
| 4 | FCPXML validates | Passes v1.11 schema | Python validation |
| 5 | Brand compliance | 100% Sacred Words, correct palette | Brand audit |
| 6 | Thumbnail ready | Final frame or photo selected | Image file |
| 7 | SEO package finalized | Title, description, tags complete | Metadata file |

---

## Phase 5 — Publish & Distribution (2-4 weeks)

> **Agents**: Bilibili Strategist, Xiaohongshu Specialist, SEO Architect | **Gate Keepers**: Studio Producer + Analytics

### Objective
Coordinate go-to-market execution across all channels. Maximum impact at launch.

### Pre-Conditions
- [ ] Phase 4 Quality Gate passed (READY verdict)
- [ ] All export files generated
- [ ] Thumbnail finalized
- [ ] SEO package complete

### Launch Timeline

#### T-3: Pre-Publish
```
ACTIVATE SEO Architect:
- Finalize all metadata (title, description, tags, chapters)
- Queue content in publishing platforms
- Prepare response templates for anticipated comments

ACTIVATE Bilibili Strategist:
- Seed danmaku strategy planned
- Community warm-up in 动态 posts
- Cross-promotion to WeChat/Weibo scheduled

ACTIVATE Xiaohongshu Specialist:
- Adapt content for 图文 posts
- Schedule optimal posting time (7-9 PM China time)
```

#### T-0: Publish Day
```
Hour 0: Publish
- Upload to primary channel (Bilibili / YouTube)
- Verify processing complete
- Set thumbnail and metadata

Hour 1: Community Activation
- Seed initial danmaku/comments
- Respond to early engagement
- Monitor initial metrics

Hour 2-8: Monitor & Response
- Track engagement rates
- Respond to comments
- Monitor for any technical issues
```

#### T+1 to T+7: Post-Publish
```
Daily:
- Analytics review (views, engagement, retention)
- Community management (comments, feedback)
- Cross-platform performance comparison
- Shorts / vertical clip performance tracking
```

### Quality Gate Checklist

| # | Criterion | Evidence Source | Status |
|---|-----------|----------------|--------|
| 1 | Video published successfully | Platform confirmation | ☐ |
| 2 | Thumbnail and metadata correct | Visual verification | ☐ |
| 3 | Initial engagement positive | Analytics dashboard | ☐ |
| 4 | No technical issues reported | Community feedback | ☐ |
| 5 | Cross-platform posts live | Platform checks | ☐ |

---

## Phase 6 — Operate & Evolve (Ongoing)

> **Agents**: All | **Governance**: Studio Producer

### Objective
Sustained content operations with continuous improvement.

### Operational Cadences

| Frequency | Activity | Output |
|-----------|----------|--------|
| **Weekly** | Performance analysis per channel | Weekly Analytics Report |
| **Weekly** | Content pipeline review | Next week's production plan |
| **Bi-Weekly** | A/B test results (thumbnails, titles) | Experiment Summary |
| **Monthly** | Curriculum gap re-audit | Updated Wiki Coverage Report |
| **Quarterly** | Channel strategy review | Quarterly Strategic Review |

### Continuous Improvement Loop

```
MEASURE (Analytics per channel)
    |
    v
ANALYZE (Studio Producer + Channel Strategists)
    |
    v
PLAN (Studio Producer + Script Architect)
    |
    v
BUILD (Phase 3 Script→Edit→Review loop)
    |
    v
VALIDATE (Studio Producer quality gate)
    |
    v
PUBLISH (Channel-specific distribution)
    |
    v
MEASURE (back to start)
```

---

*This playbook governs all DeParadigm Media video production. Re-activation of any phase is permitted for iterative content improvement.*
