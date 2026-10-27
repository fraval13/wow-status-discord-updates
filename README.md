# WoW character status and Discord updates

An independent project for friends to opt in to sharing WoW character progress
and milestones in Discord, regardless of guild membership.

**Status: planning.** See the [project plan](character-logs-plan.md) for scope,
privacy controls, implementation milestones, and acceptance checks.

## Intended pipeline

WoW addon → local companion uploader → authenticated service and database → Discord bot.

The initial version uses SavedVariables exported on `/reload` or logout, so
announcements are delayed and character commands show last-known status.

## First milestone

Confirm the gaming operating system, exact WoW edition and build, addon path,
and test Discord channel. Then prove one real level-up can travel through the
pipeline after export without creating duplicate announcements.

Client-specific APIs must be validated before implementing additional events.
Classic testing does not establish compatibility with other WoW clients.

## Repository scope

This repository contains the character logs plan. The Forever news feed bot is
a separate project and is not included here.
