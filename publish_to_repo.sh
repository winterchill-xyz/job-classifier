#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
src="$repo_root/models/job_classifier"
remote="${JOB_CLASSIFIER_REMOTE:-git@github.com:winterchill-xyz/job-classifier.git}"
branch="${JOB_CLASSIFIER_BRANCH:-main}"
message="${JOB_CLASSIFIER_COMMIT_MESSAGE:-chore: snapshot job classifier}"
author_name="${JOB_CLASSIFIER_GIT_AUTHOR_NAME:-Valerii Iatsko}"
author_email="${JOB_CLASSIFIER_GIT_AUTHOR_EMAIL:-viatsko@viatsko.me}"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

git clone "$remote" "$tmp/repo"
git -C "$tmp/repo" checkout -B "$branch"

rsync -a --delete \
  --exclude='.git' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  "$src/" "$tmp/repo/"

git -C "$tmp/repo" config user.name "$author_name"
git -C "$tmp/repo" config user.email "$author_email"
git -C "$tmp/repo" add -A

if git -C "$tmp/repo" diff --cached --quiet; then
  echo "job-classifier snapshot unchanged"
  exit 0
fi

GIT_AUTHOR_NAME="$author_name" \
GIT_AUTHOR_EMAIL="$author_email" \
GIT_COMMITTER_NAME="$author_name" \
GIT_COMMITTER_EMAIL="$author_email" \
git -C "$tmp/repo" commit -m "$message"

git -C "$tmp/repo" push "$remote" "HEAD:$branch"
