---
title: explainer-structure
date: 2026-06-10
tags:
  - ingested
source: explainer-structure.md
---
# Explainer Structure (Edutainment)

## Goal
The viewer should actually understand the concept by the end. Sarcasm can make it stick, but it never replaces the teaching.

## Structure

### 1. Hook
Pose the question or misconception. "You've been told recursion is hard. It's not. It's just management."

### 2. The Core Idea
State it plainly and correctly, once, up front.
- **Core Idea:** Recursion is when a function calls itself repeatedly until it reaches a base case.

### 3. Build Understanding
One step at a time, start with the simplest case. Don't skip rungs.
- **Step 1:** Understand the base case. This is the condition that stops the recursion.
- **Step 2:** Understand the recursive case. This is where the function calls itself with a modified argument.
- **Step 3:** Combine the base case and recursive case to form the complete function.

### 4. Analogy
A vivid, everyday comparison that maps to the concept accurately. A bad analogy that misleads is worse than none.
- **Analogy:** Think of recursion as a stack of plates. Each plate (function call) goes on top of the previous one. When you add a plate (recursive call), you put it on top. When you remove a plate (base case), you take it off the top.

### 5. The Catch / Nuance
The part everyone gets wrong — address it with attitude.
- **Catch:** People often confuse recursion with iteration. While both involve repetition, recursion is about calling the same function again and again, while iteration is about looping through a set of instructions.

### 6. Recap
Restate the core idea now that it's earned. Optional teach-back prompt.
- **Recap:** Recursion is when a function calls itself repeatedly until it reaches a base case. It's just management, like stacking plates.
- **Teach-Back Prompt:** Can you explain recursion using the stack of plates analogy?<|im_end|>
