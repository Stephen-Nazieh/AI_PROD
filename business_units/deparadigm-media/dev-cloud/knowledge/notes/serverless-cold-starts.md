---
title: serverless-cold-starts
date: 2026-06-10
tags:
  - ingested
source: serverless-cold-starts.md
---
# Serverless Cold Starts — Mitigation

A cold start occurs when a serverless platform spins up a new instance to handle a request because no warm instance is available. Latency is caused by container initialization, runtime boot, and your application's startup code.

## Google Cloud Run

- **Min-instances > 0**: Keeps warm instances available.
- **Startup CPU Boost**: Accelerates the startup process.
- **Small Container Image**: Reduces boot time.
- **Lazy-load Heavy Dependencies**: Delays loading heavy dependencies until needed.
- **2nd-Gen Execution Environment**: Faster boots.

Concurrency > 1 means one instance can serve multiple requests, reducing the number of cold starts.

## AWS Lambda

- **Provisioned Concurrency**: Ensures predictable latency by keeping instances warm.
- **Small Package**: Reduces boot time.
- **Avoid Heavy Work Outside Handler**: Minimizes cold start impact.
- **SnapStart (Java)**: Restores a snapshot to skip initialization.
- **Reserved Concurrency**: Caps scaling but does not pre-warm instances.

## Rule of Thumb

Cold starts primarily impact p99 latency, not throughput. It is crucial to measure the impact before paying for always-on capacity.<|im_end|>
