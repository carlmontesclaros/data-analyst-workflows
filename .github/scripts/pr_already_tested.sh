#!/usr/bin/env bash
# Decide whether the test jobs can be skipped on a push to main.
#
#   pr_already_tested.sh <repo owner/name> <commit sha>
#
# Prints "skip=true" when the PR that was merged as <sha> already passed the Windows and Mac test jobs on its head commit and
# the tree of <sha> is identical to the tree of that head commit, otherwise "skip=false". Every doubt (no PR, trees differ,
# a check missing or not green, an API error) is "skip=false", so the tests run exactly as before. Comparing trees is what
# makes this safe without branch protection: if main moved before the merge, the trees differ.
# Needs the gh CLI with GH_TOKEN set. Progress notes go to stderr; stdout is only the skip line.
set -u

repo=${1:?usage: pr_already_tested.sh <owner/name> <sha>}
sha=${2:?usage: pr_already_tested.sh <owner/name> <sha>}

run() { echo "skip=false"; echo "run the tests: $1" >&2; exit 0; }

# the PR merged as this commit (a squash or rebase merge puts the PR's content in one new commit on main)
prs=$(gh api "repos/$repo/commits/$sha/pulls" --jq '[.[] | select(.merged_at != null and .merge_commit_sha == "'"$sha"'")]') \
    || run "could not list the pull requests of $sha"
[ "$(jq length <<<"$prs")" = 1 ] || run "$sha is not the merge commit of exactly one pull request"
head=$(jq -r '.[0].head.sha' <<<"$prs")
number=$(jq -r '.[0].number' <<<"$prs")

# the same files, byte for byte
merged_tree=$(gh api "repos/$repo/git/commits/$sha" --jq .tree.sha) || run "could not read the tree of $sha"
head_tree=$(gh api "repos/$repo/git/commits/$head" --jq .tree.sha) || run "could not read the tree of PR #$number head $head"
[ -n "$merged_tree" ] && [ "$merged_tree" = "$head_tree" ] || run "tree $merged_tree of $sha differs from tree $head_tree of PR #$number head $head"

# both test jobs concluded success on the PR head (the latest run of each job counts, so a green re-run wins over an old red one)
checks=$(gh api "repos/$repo/commits/$head/check-runs?per_page=100" --paginate --jq '.check_runs[] | {name, conclusion, completed_at}' | jq -s .) \
    || run "could not read the checks of PR #$number head $head"
for job in "test (windows-latest)" "test (macos-latest)"; do
    conclusion=$(jq -r --arg job "$job" '[.[] | select(.name == $job and .completed_at != null)] | sort_by(.completed_at) | last | .conclusion // "missing"' <<<"$checks")
    [ "$conclusion" = success ] || run "'$job' is $conclusion on PR #$number head $head"
done

echo "skip=true"
echo "skip the tests: $sha has the same tree as PR #$number head $head, and both test jobs passed there" >&2
