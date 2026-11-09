"use client";
import { useMe } from "@northcx/api-client";
import { ComingSoon, GlassCard, Loading, PageHeader } from "@northcx/ui";

export default function Profile() {
  const { me, failed } = useMe();
  if (!me && !failed) return <Loading />;
  return (
    <>
      <PageHeader title="Profile" subtitle="Who you are to NorthCX." />
      <div className="grid gap-4 lg:grid-cols-2">
        <GlassCard title="About you">
          {me ? (
            <dl className="grid grid-cols-[8rem_1fr] gap-y-2 text-sm">
              <dt className="text-muted">Name</dt><dd>{me.name}</dd>
              <dt className="text-muted">Role</dt><dd>{me.role.replace("_", " ")}</dd>
              <dt className="text-muted">Sign-in</dt><dd>{me.openMode ? "None (open mode)" : me.keyId ? `Key ${me.keyId}` : "Single sign-on or bootstrap key"}</dd>
            </dl>
          ) : <p className="text-sm text-muted">The server did not say who you are.</p>}
        </GlassCard>
        <GlassCard title="What your role may do">
          {me ? <ul className="flex flex-wrap gap-1.5">{me.permissions.slice().sort().map((p) => <li key={p} className="pill font-mono">{p}</li>)}</ul> : null}
          <p className="mt-3 text-xs text-muted">Roles come from your key or your identity provider and cannot be edited here.</p>
        </GlassCard>
      </div>
      <div className="mt-4"><ComingSoon title="Instructions, persona, personal context, skills and assistants"
        what="Standing instructions, a writing style, personal context, reusable skills and assistants you build for your own work, with memory and an activity log."
        needs="the staff assistant backend (E5); see the Admin platform design" /></div>
    </>
  );
}
