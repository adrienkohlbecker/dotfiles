export const meta = {
  name: 'apply_findings',
  description: 'Apply operator-selected patch_review findings, one sequential agent per patch group, one commit per finding',
  whenToUse:
    'After patch_review or role_simplify, once the operator has picked finding numbers. Never pushes.',
  phases: [
    { title: 'Load', detail: 'read findings.json and resolve the selection' },
    { title: 'Apply', detail: 'one agent per group, sequential, same tree' },
  ],
}

// args: {dir, select, notes?, repo?, lint?, findings?}
//   dir      patch_review output directory holding findings.json (and applied.json)
//   select   "all", "1-5,7 9", optionally "... except 16 37"
//   notes    operator guidance: a string for every finding, or {"<n>": text}
//   findings the consolidated array, to skip reading findings.json
const opts = args ?? {}
if (!opts.dir) throw new Error('apply_findings needs dir (the patch_review output directory)')
if (!opts.select) throw new Error('apply_findings needs select, e.g. "1-5,7" or "all except 16 37"')
const repo = opts.repo ?? 'the current repository'
const lint = opts.lint ?? 'mise run lint'

function numbers(spec) {
  const out = new Set()
  for (const part of spec.split(/[\s,]+/).filter(Boolean)) {
    const m = part.match(/^(\d+)(?:-(\d+))?$/)
    if (!m) throw new Error(`bad selection token: ${part}`)
    const [a, b] = [Number(m[1]), Number(m[2] ?? m[1])]
    for (let n = Math.min(a, b); n <= Math.max(a, b); n++) out.add(n)
  }
  return out
}

const FINDINGS = {
  type: 'object',
  properties: { findings: { type: 'array', items: { type: 'object' } } },
  required: ['findings'],
}

phase('Load')
const all =
  opts.findings ??
  (
    await agent(
      `Read ${opts.dir}/findings.json and return its array unchanged as findings. Do not summarise or edit any entry.`,
      { label: 'load', schema: FINDINGS },
    )
  )?.findings
if (!all?.length) throw new Error(`no findings in ${opts.dir}/findings.json`)

const [include, exclude = ''] = String(opts.select).toLowerCase().split(/\bexcept\b/)
const wanted = include.trim() === 'all' ? new Set(all.map((f) => f.n)) : numbers(include)
for (const n of numbers(exclude)) wanted.delete(n)
const selected = all.filter((f) => wanted.has(f.n))
const unknown = [...wanted].filter((n) => !all.some((f) => f.n === n))
if (unknown.length) throw new Error(`selection names findings that do not exist: ${unknown.join(', ')}`)

const noteFor = (n) => (typeof opts.notes === 'string' ? opts.notes : opts.notes?.[String(n)])
const groups = new Map()
for (const f of selected.sort((a, b) => a.n - b.n)) {
  const note = noteFor(f.n)
  groups.set(f.patch, [...(groups.get(f.patch) ?? []), note ? { ...f, operator_note: note } : f])
}
log(`${selected.length} finding(s) in ${groups.size} group(s)`)

const RESULT = {
  type: 'object',
  properties: {
    applied: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          n: { type: 'array', items: { type: 'integer' }, description: 'findings in this commit (one, unless inseparable)' },
          sha: { type: 'string' },
          subject: { type: 'string' },
          validation: { type: 'string', description: 'what ran and its result' },
        },
        required: ['n', 'sha', 'subject', 'validation'],
      },
    },
    deferred: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          n: { type: 'integer' },
          reason: { type: 'string' },
          recommended_fix: { type: 'string', description: 'the edit you would make and why, for the operator to approve' },
        },
        required: ['n', 'reason', 'recommended_fix'],
      },
    },
    lint_preexisting: { type: 'string', description: 'lint failures not caused by these changes, if any' },
  },
  required: ['applied', 'deferred'],
}

phase('Apply')
const results = []
for (const [patch, items] of groups) {
  const before = results.flatMap((r) => r.applied.map((a) => `${a.sha} ${a.subject}`))
  const r = await agent(
    `Apply these operator-selected review findings in ${repo}, working in the existing tree (no worktree, no branch switch).

Follow "Apply selected findings" in ~/.claude/skills/simplify_review/SKILL.md and the Commit Protocol and Hard Scope Denylist in ~/.claude/skills/improve/references/consolidate-and-act.md, with these overrides:
- The operator's selection through this workflow is the approval for each concrete finding: do not wait for a plan or diff sign-off.
- Do not apply, and instead return under "deferred" with a recommended fix, any finding that is kind "flag", is "suspected" with evidence you cannot confirm in the tree, conflicts with an operator_note, or needs a denylisted path.
- An operator_note is binding guidance for that finding.
- One commit per finding. Bundle two findings only when they cannot be separated, and list both numbers.
- Before each commit, run \`${lint}\` and the narrowest relevant test. Fix failures your change caused inside that commit. Record failures that exist without your change in lint_preexisting and commit anyway.
- After each commit, update ${opts.dir}/applied.json: a JSON array of {n, sha, subject}, merged by n, written atomically (temp file in the same directory, then rename).
- Never push, amend a commit you did not create in this run, or touch unrelated worktree changes.
${before.length ? `\nEarlier groups in this run already committed:\n${before.join('\n')}\n` : ''}
Patch group ${patch}. Findings:
${JSON.stringify(items, null, 1)}`,
    { label: `apply:${patch}`, schema: RESULT },
  )
  if (!r) {
    log(`group ${patch} returned nothing; stopping so later groups do not build on an unknown tree state`)
    return { applied: results.flatMap((x) => x.applied), deferred: results.flatMap((x) => x.deferred), failed_group: patch }
  }
  results.push(r)
  log(`group ${patch}: ${r.applied.length} commit(s), ${r.deferred.length} deferred`)
}

return {
  applied: results.flatMap((r) => r.applied),
  deferred: results.flatMap((r) => r.deferred),
  lint_preexisting: results.map((r) => r.lint_preexisting).filter(Boolean),
}
