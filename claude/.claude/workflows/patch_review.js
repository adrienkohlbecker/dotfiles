export const meta = {
  name: 'patch_review',
  description: 'Group a diff into patches, review each with skill-backed lenses, return one numbered findings list',
  whenToUse:
    'Review a commit range patch by patch (simplify, Codex, improve lenses). Stops at the numbered list; apply the selection with apply_findings.',
  phases: [
    { title: 'Group', detail: 'partition the diff into self-contained patches' },
    { title: 'Review', detail: 'one agent per patch and lens, read-only' },
    { title: 'Consolidate', detail: 'dedupe, order and number the findings' },
  ],
}

// args: a range string, or
//   {range, repo?, max_files?, lenses?, plannotator?, round?, out?, targets?}
// `targets` ([{id, title, files}]) skips grouping and reviews files whole
// (role_simplify uses it); `out` then names the output directory.
const opts = typeof args === 'string' ? { range: args } : (args ?? {})
if (!opts.range && !opts.targets) throw new Error('patch_review needs a range (e.g. "abc123..HEAD") or targets')

const maxFiles = opts.max_files ?? 20
const round = opts.round ?? 1
const repo = opts.repo ?? 'the current repository (git rev-parse --show-toplevel)'
const slug = (opts.out ?? opts.range).replace(/[^A-Za-z0-9]+/g, '_').replace(/^_|_$/g, '')
const dirName = round > 1 ? `${slug}_r${round}` : slug
const dirExpr = `"$(git rev-parse --path-format=absolute --git-common-dir)/patch_review/${dirName}"`
const priorDirs = Array.from({ length: round - 1 }, (_, i) => (i === 0 ? slug : `${slug}_r${i + 1}`))

const IMPROVE = ['analysis', 'upstream', 'simplification', 'security', 'prior-art']
const lenses = (opts.lenses ?? ['simplify', 'codex']).flatMap((l) => (l === 'improve' ? IMPROVE : [l]))
if (opts.plannotator) lenses.push('operator')
for (const l of lenses) {
  if (!['simplify', 'codex', 'operator', ...IMPROVE].includes(l)) throw new Error(`unknown lens: ${l}`)
}

const PATCHES = {
  type: 'object',
  properties: {
    dir: { type: 'string', description: 'absolute output directory' },
    base: { type: 'string' },
    tip: { type: 'string' },
    patches: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          id: { type: 'string', description: 'two-digit order, e.g. "01"' },
          title: { type: 'string' },
          summary: { type: 'string', description: 'what the change does and why, 2-3 sentences' },
          files: { type: 'array', items: { type: 'string' } },
          related: { type: 'array', items: { type: 'string' }, description: 'files in other patches this one interacts with' },
          path: { type: 'string', description: 'absolute path of the .patch file' },
        },
        required: ['id', 'title', 'summary', 'files', 'path'],
      },
    },
  },
  required: ['dir', 'base', 'tip', 'patches'],
}

const FINDING_PROPS = {
  file: { type: 'string', description: 'repo-relative path' },
  line: { type: ['integer', 'null'] },
  severity: { enum: ['critical', 'high', 'medium', 'low'] },
  issue: { type: 'string', description: '1 sentence' },
  why: { type: 'string', description: 'why it matters, 1 sentence' },
  change: { type: 'string', description: 'concrete proposed change, with file:line' },
  risk: { type: 'string', description: 'behaviour change and tests to update' },
  evidence: { type: 'string', description: 'what you read or ran that confirms it' },
  confidence: { enum: ['verified', 'suspected'] },
  kind: { enum: ['fix', 'flag'], description: 'fix = concrete and ready to apply; flag = needs a decision or missing evidence' },
  change_class: { enum: ['B', 'M', 'D'], description: 'B behaviour-preserving, M minor behaviour change, D drops a feature' },
}
const FINDING_REQUIRED = ['file', 'line', 'severity', 'issue', 'why', 'change', 'confidence', 'kind', 'change_class']

const LENS_FINDINGS = {
  type: 'object',
  properties: {
    findings: { type: 'array', items: { type: 'object', properties: FINDING_PROPS, required: FINDING_REQUIRED } },
    biggest_win: { type: 'string' },
  },
  required: ['findings'],
}

const CONSOLIDATED = {
  type: 'object',
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          n: { type: 'integer' },
          patch: { type: 'string', description: 'patch id the finding belongs to' },
          sources: { type: 'array', items: { type: 'string' } },
          ...FINDING_PROPS,
        },
        required: ['n', 'patch', 'sources', ...FINDING_REQUIRED],
      },
    },
    markdown: { type: 'string', description: 'the numbered list as presented in findings.md' },
  },
  required: ['findings', 'markdown'],
}

const skill = (name) => `~/.claude/skills/${name}/SKILL.md`

const priorNote = priorDirs.length
  ? `\nThis is review round ${round}. Earlier rounds' findings are in findings.json (and what landed in applied.json, if present) under these sibling directories of the output directory: ${priorDirs.join(', ')}. Read them first. Do not repeat a finding that was raised before unless it is still unresolved and you have new evidence. Be more ambitious than the earlier rounds: look for structural simplification, whole features or layers to drop, and cross-file merges, not line-level polish.\n`
  : ''

function scopeOf(p) {
  if (opts.targets) {
    return `Target: ${p.title} (${p.id}). Review these files as a whole:\n${p.files.join('\n')}`
  }
  return [
    `Target: patch ${p.id} "${p.title}" of ${opts.range} in ${repo}.`,
    `Patch file (authoritative snapshot of the change): ${p.path}`,
    `Summary: ${p.summary}`,
    `Changed files:\n${p.files.join('\n')}`,
    p.related?.length ? `Related files in other patches:\n${p.related.join('\n')}` : '',
    'Review the change in the patch, reading the surrounding code in the live checkout as needed.',
  ].join('\n')
}

const RETURN_RULES = `Read-only: do not edit files, stage, commit, or run mutating commands.
Ignore any "stop and wait for the user" step: return the findings through the schema instead.
Check each finding against HEAD too, and omit it if a later commit already fixes it.
Return only real findings; an empty list is a valid result.`

function lensPrompt(lens, p, dir) {
  const scope = scopeOf(p)
  if (lens === 'simplify') {
    return `Follow the review workflow in ${skill('simplify_review')} (and the improve contract it references), steps 1-4.
${scope}
The 20-file narrowing rule of the contract does not apply: the target was already scoped.
${priorNote}${RETURN_RULES}`
  }
  if (lens === 'codex') {
    const raw = `${dir}/${p.id}_codex${round > 1 ? `_r${round}` : ''}.txt`
    const diff = opts.targets
      ? `Write the diff snapshot yourself: for each target file, \`git diff --no-index -- /dev/null <file> || true\`, so Codex reviews the files whole.`
      : `Skip step 1: the diff snapshot is the patch file.`
    return `Follow ${skill('cross_review')} as Claude (run Codex read-only).
${scope}
${diff} Describe the scope as "${opts.targets ? p.title : `patch ${p.id} of ${opts.range}`}".
${priorDirs.length ? `Add this paragraph to the Codex prompt:\n${priorNote}` : ''}
Run codex with its output redirected to ${raw} and wait for it to exit, bounded to 30 minutes. If the Bash sandbox blocks Codex's network or ~/.codex access, rerun that one command with the sandbox disabled.
Instead of returning the review verbatim, map every Codex finding into the schema without filtering or softening it; keep Codex's severity, put its evidence in \`evidence\`, and mark it suspected unless Codex verified it. The raw text stays in ${raw}.
${RETURN_RULES}`
  }
  if (lens === 'operator') {
    const tailscale = opts.plannotator === 'tailscale' ? ' --tailscale' : ''
    return `Open the patch for the operator in Plannotator and turn their annotations into findings.
${scope}
Run \`plannotator review --patch-file ${p.path} --json${tailscale}\` in the background with stdout to ${dir}/${p.id}_plannotator.json and wait for it to exit (it blocks until the operator submits; allow up to 2 hours). Do not kill it.
If the decision is "approved" with no notes or "dismissed", return no findings. Otherwise make one finding per annotation: the operator's words go in \`issue\` and \`change\` verbatim, severity medium unless they say otherwise, kind fix, confidence verified.
${RETURN_RULES}`
  }
  return `Follow ${skill(`improve-${lens}`)} (and the shared improve contract it references).
${scope}
The 20-file narrowing rule of the contract does not apply: the target was already scoped.
${priorNote}${RETURN_RULES}`
}

phase('Group')
let grouped
if (opts.targets) {
  grouped = await agent(
    `In ${repo}, create the directory ${dirExpr} (mkdir -p) and print its absolute path. Return it as dir, with base and tip both set to \`git rev-parse HEAD\` and patches set to this list unchanged, path "" for each:\n${JSON.stringify(opts.targets)}`,
    { label: 'prepare', schema: PATCHES },
  )
} else {
  grouped = await agent(
    `Group the diff of ${opts.range} in ${repo} into reviewable patch files.

1. Resolve the range: a single revision R means R..HEAD; A...B means merge-base(A,B)..B. Record base and tip as full SHAs.
2. Output directory: ${dirExpr}. Recreate it empty (rm -rf then mkdir -p) and use its absolute path.
3. Partition the changed files (\`git diff --name-only --find-renames base tip\`) into self-contained patches of at most ${maxFiles} files each:
   - group by topic: one coherent change per patch (a feature, a refactor, a role), using commit messages and file contents to decide;
   - group small related changes together rather than making many tiny patches;
   - never split a single commit that touches more than ${maxFiles} files across patches; let that patch exceed the limit;
   - every changed file lands in exactly one patch; keep both sides of a rename in the same patch;
   - order patches so earlier ones do not depend on later ones where possible.
   For each patch, list in "related" the files from other patches it interacts with.
4. Write each patch as NN_<slug>.patch: \`git diff --binary --find-renames base tip -- <files>\`.
5. Verify the patches rebuild the tip: with a temporary index (GIT_INDEX_FILE=$(mktemp)), \`git read-tree base\`, \`git apply --cached\` each patch in order, then compare \`git write-tree\` with \`git rev-parse tip^{tree}\`. Fix the grouping until they match. Remove the temporary index.
6. Write patches.json (this schema's object) in the directory.
Do not modify the worktree, the real index, or any ref.`,
    { label: 'group', schema: PATCHES },
  )
}
if (!grouped?.patches?.length) throw new Error('grouping returned no patches')
const dir = grouped.dir
log(`${grouped.patches.length} patch(es) in ${dir}; lenses: ${lenses.join(', ')}`)

const reviews = await pipeline(grouped.patches, (p) =>
  parallel(
    lenses.map((lens) => () =>
      agent(lensPrompt(lens, p, dir), { label: `${lens}:${p.id}`, phase: 'Review', schema: LENS_FINDINGS }).then((r) => ({
        lens,
        patch: p.id,
        findings: r?.findings,
      })),
    ),
  ),
)

const missing = []
const byKey = new Map()
for (const r of reviews.flat()) {
  if (!r?.findings) {
    missing.push(`${r?.lens}:${r?.patch}`)
    continue
  }
  for (const f of r.findings) {
    const key = `${f.file}:${f.line ?? ''}`
    const seen = byKey.get(key)
    if (seen) seen.duplicates.push({ source: r.lens, ...f })
    else byKey.set(key, { patch: r.patch, sources: [r.lens], ...f, duplicates: [] })
  }
}
if (missing.length) log(`no result from: ${missing.join(', ')}`)
const merged = [...byKey.values()]
if (!merged.length) return { dir, patches: grouped.patches.length, missing, findings: [], markdown: 'No findings.' }

phase('Consolidate')
const consolidated = await agent(
  `Consolidate these review findings for ${opts.range ?? opts.out} in ${repo} into one numbered list.
Output directory: ${dir}
Patches: ${JSON.stringify(grouped.patches.map(({ id, title }) => ({ id, title })))}

Follow the Merge, Quarantine and Present sections of ~/.claude/skills/improve/references/consolidate-and-act.md, with these specifics:
- Findings sharing a file:line are already grouped: each entry's \`duplicates\` holds the other lenses' versions. Merge each entry with its duplicates into one finding, union the sources, keep the strongest severity and the most concrete change.
- Also merge findings at different lines that describe the same issue, and turn conflicting proposals for the same code into one finding with kind "flag" that states both options.
- Lens names map to sources: simplify, codex, operator, and the improve lenses by name.
- Drop findings whose evidence says a later commit already fixes them at HEAD; end the markdown with one line naming how many were dropped and the fixing commits.
- Order: security first, then by patch order, then severity. Number from 1 with no gaps.
${priorDirs.length ? `- Drop findings already raised in earlier rounds (findings.json under ${priorDirs.join(', ')}, siblings of the output directory) unless still unresolved with new evidence.\n` : ''}- Do not invent findings or re-review the code; you may open a file to judge whether two findings are the same.
Write findings.json (the findings array) and findings.md (the markdown) into the output directory. The markdown is a numbered list, one item per finding: **n. severity, \`file:line\`** (patch, sources) issue, then the change and risk on indented lines; append [flag] to findings that need a decision.

Findings:
${JSON.stringify(merged)}`,
  { label: 'consolidate', schema: CONSOLIDATED },
)
if (!consolidated) throw new Error(`consolidation failed; lens results are in this run's journal (${merged.length} merged findings)`)

return { dir, patches: grouped.patches.length, missing, findings: consolidated.findings, markdown: consolidated.markdown }
