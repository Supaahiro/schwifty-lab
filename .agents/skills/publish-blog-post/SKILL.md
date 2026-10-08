---
name: publish-blog-post
description: Prepare or publish a schwifty-lab blog article, including its lab assets, GitHub Pages catalog entry, series links, and the BlogPost manifest in k8s-platform. Use when adding an article or completing its publication across these repositories.
---

# Publish a schwifty-lab Article

Coordinate the article's three representations: the full Markdown and assets,
the Jekyll catalog entry, and the Kubernetes blog catalog resource. Follow the
user's requested stopping point: preparing reviewable files and publishing them
are distinct outcomes.

## Locate the existing content

Read applicable repository instructions and check working-tree changes before
editing. The paths below describe the current setup; verify them when publishing
because hosting and deployment configuration may change.

| Purpose | Current location |
|---|---|
| Full English article | `blog-posts/YYYYMMDD-topic/article_EN.md` in schwifty-lab |
| Cover | `article.webp` beside the article |
| Runnable examples | The article's `manifests/`, and `src/` when needed |
| Jekyll catalog entry | `_posts/YYYY-MM-DD-topic.md` in schwifty-lab |
| CKAD series index | `blog-posts/20251019-ckad/article_EN.md` |
| Kubernetes catalog | `deploy/apps/blog/content/posts/` in k8s-platform |
| Catalog registration | `kustomization.yaml` in that posts directory |

The owner's current platform checkout is
`C:/repos/github/k8s-platform/wt0`. Resolve another checkout if supplied. Read its
repository instructions, `deploy/CONVENTIONS.md`, and the current BlogPost CRD at
`deploy/apps/blog/base/crds/blogapi-post-v1alpha2.yaml` when editing that catalog.

Compare the latest article and its two catalog entries, rather than assuming an
old prompt template still reflects the live schema or hosting URLs. Useful
examples are `blog-posts/20261008-ckad/`, `_posts/2026-10-08-ckad.md` and the matching
`20261008-ckad-authentication-authorization-admission-control.yaml` in k8s-platform.

## Write the article and lab

Use the requested topic, language and publication date. English is the current
CKAD series convention. If no date is supplied, use the current date and state it.
For CKAD, the folder suffix and catalog filename suffix are `ckad`.

The full article has YAML frontmatter with `layout: default`, title, ISO date,
`categories: [ckad, kubernetes]`, `author: Hiro`, image and summary. Other subjects
use the categories of their own series. CKAD titles begin `CKAD Preparation`.

Existing articles introduce the requirement and its place in the series, link
to the series index and relevant previous chapter, explain prerequisites, show
how to get the resources, then teach through runnable examples and expected
results. Include cleanup scoped to the lab resources. Adapt section titles and
length to the subject; there is no fixed outline to reproduce verbatim.

Number YAML files by their order of use. Ensure filenames and code excerpts match
the checked-in examples. If using the `k` alias, define it; otherwise `kubectl`
works without shell setup. Identify the shell for nonportable examples. Explain
intentional failure cases so readers can distinguish a successful exercise from
a broken lab. Verify changing technical details against primary documentation
and link it near the explanation.

Use a supplied cover or create one consistent with neighboring articles. Current
covers are wide WebP illustrations, typically dark technical imagery without
text. Save the actual asset before referencing it; a prompt alone is not a cover.
Other languages are separate `article_<LANG>.md` files when requested.

## Keep the catalogs consistent

### GitHub Pages

Create `_posts/YYYY-MM-DD-topic.md` with frontmatter only. Copy the article's
metadata and add:

```yaml
link: "blog-posts/YYYYMMDD-topic/article_EN.html"
```

The `link` points to Jekyll's rendered HTML page, not the Markdown source. Current
image URLs in both frontmatters use
`https://supaahiro.github.io/schwifty-lab/blog-posts/YYYYMMDD-topic/article.webp`.
Keep shared title, date, summary, author, categories and image identical. The full
article does not need the catalog's `link` field.

For CKAD, turn the corresponding plain-text requirement in the series index
into a link to the new `.html` page. Preserve unrelated roadmap entries.

### Local Kubernetes blog

Create one file named `YYYYMMDD-topic-descriptive-slug.yaml` in the platform posts
directory, with `apiVersion: blog.supaahiro.io/v1alpha2`, `kind: BlogPost`:

- `metadata.name` and `spec.id` equal the filename without `.yaml`.
- `spec.title` uses the topic title; existing CKAD manifests omit the series prefix.
- `spec.summary` matches the article summary.
- `spec.previewImage` currently uses `https://www.schwifty-lab.org/blog-posts/.../article.webp`.
- `spec.contentUrl` is a language-to-URL map, with `en` pointing to
  `https://www.schwifty-lab.org/blog-posts/.../article_EN.md`.
- `spec.publishedOn` uses the same publication date in UTC ISO format, following
  existing date-only entries such as `2026-10-08T00:00:00Z`.
- `spec.author` is `Hiro`; CKAD uses `spec.categoryId: ckad-preparation`.
- `spec.relatedPostsIds` contains actual IDs from neighboring manifests. Include
  relevant series context, especially the index and previous related chapter.
- Existing manifests set `status.published: true` and `status.indexed: true`.
  These are catalog fields, not evidence that content has been deployed.

Add the new filename once to `posts/kustomization.yaml`. Do not infer related IDs
from article titles: historical spellings may differ. Additional translations
need corresponding keys in `contentUrl` only when the files exist.

The custom host serves raw Markdown to the application; GitHub Pages serves
rendered HTML. Publishing a `_posts` entry or a BlogPost manifest does not prove
that raw Markdown and its cover are available on the custom host. Inspect the
current static-host upload/sync mechanism when that publication step is in scope.

## Validate and hand over

Check YAML and frontmatter parsing, matching metadata, referenced local assets,
series links, related IDs, and registration in the Kustomization. Use the affected
repository's yamllint configuration and preserve its line endings.

```powershell
yamllint -c .yamllint.yml blog-posts/YYYYMMDD-topic/manifests
kubectl kustomize C:/repos/github/k8s-platform/wt0/deploy/apps/blog/content/posts
```

Validate changed platform YAML with that repository's `.yamllint.yml`. A
Kustomize render checks resource assembly; it does not validate every CRD field.
Check the BlogPost against the current CRD schema as well.

Run meaningful lab commands on an appropriate disposable cluster when available,
checking both allowed and intentionally denied requests and cleaning up created
resources. State what ran and what remains untested. Do not treat a manifest
parse or client dry-run as proof of runtime behavior.

For Jekyll preview, the root `Gemfile` requires `../blog-jekyll-theme` relative to
the checkout. With Ruby/Bundler and that theme available, use `bundle install`
and `./start-dev.bat web`; `bundle exec jekyll build --config _config.local.yml`
provides a build check. Report missing prerequisites rather than claiming a
successful build. Inspect rendered headings, code, diagrams and images.

When publication is requested, use each repository's topic-branch/PR workflow
and the session's authorization. The platform content is managed through Flux;
inspect `deploy/clusters/k8c1/apps/blog/blog-content.yaml` for the actual source,
path and target namespace. A direct `kubectl apply` to the platform is not its
normal publication flow. Confirm the rendered article, image and raw content URLs
after deployment before calling the publication complete.

For a files-only request, hand over the changed files, validation results and
remaining publication steps. Preserve unrelated changes in both repositories.

This skill is maintained in both `.agents/skills/publish-blog-post/` and
`.claude/skills/publish-blog-post/`; keep their contents identical when updating
it. The current root `.gitignore` ignores `.claude/`, so explicitly report that
copy's local-only status unless the user requests versioning it.
