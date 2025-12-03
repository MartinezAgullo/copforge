# COP Forge

Modular Information Fusion System for Building Common Operational Pictures

## Description

CopForge is a modular, protocol-driven system designed to ingest heterogeneous sensor data and fuse it into a unified Common Operational Picture (COP). Built for interoperability and scalability, it leverages modern agent communication standards to create a flexible, framework-agnostic architecture. Note that the COP we are using is a toy-model one.

It is an evolution of the original [TIFDA](https://github.com/MartinezAgullo/genai-tifda) project.

<!-- Agentic mesh for the TIFDA (Tactical Information Fusion and Dissemination Agent) project -->

### What it does

1. **Multi-source Ingestion**: Accepts data from diverse sensors (radar, drones, manual reports, radio intercepts, etc) in various formats
2. **Intelligent Parsing**: Automatically detects formats and extracts entities, with LLM-powered multimodal processing for images, audio, and documents
3. **Entity Normalization**: Converts all inputs into a standardized EntityCOP format
4. **Sensor Fusion**: Merges observations from multiple sensors, deduplicates entities, and boosts confidence through multi-source confirmation
5. **COP Management**: Maintains and updates the operational picture with full audit trail

### Architecture

CopForge uses a decoupled architecture based on two protocols:

- **A2A Protocol** (Agent-to-Agent): For communication between intelligent agents that require reasoning or orchestration
- **MCP** (Model Context Protocol): For exposing deterministic tools that agents can invoke
