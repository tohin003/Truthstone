---
name: ground-claims
description: Use before writing code that relies on a function, method, class, module, file, config key, environment variable, route, CLI flag or package you have not yet seen in this repository, before stating facts about the codebase, and when a user, reviewer or tool questions such a claim. Verifies that the thing exists with the shape you expect, cites file:line, and labels anything unverified as an assumption.
license: Apache-2.0
---

# Ground claims in the repository

Go from claim to evidence, then to confidence, then to action. Never go straight from claim to action.

A claim is anything your code or your message takes for granted. For example:

- that `UserRepository.get_active_users()` exists
- that `paginate()` accepts `page_size`
- that `settings.CACHE_TTL` is defined
- that a package is installed
- that `/api/orders` is a route
- that a test for this behavior already exists

## Verify before relying on it

Check the repository, not your memory. Search for the definition and open it.

| Claim | Where to look |
|---|---|
| A function or class exists | Its definition (`def`, `class`, `function`, `export`) |
| A method or attribute exists on a type | The class body and every base class. For generated or framework bases such as ORM models and schema classes, check the framework's own source or the documentation for the installed version |
| `from our_module import name` works | `our_module` defines or re-exports `name` |
| A call signature | The parameters, defaults and return type at the definition |
| A third-party package | Declared in the project manifest (`pyproject.toml`, `requirements*.txt`, `package.json`, `go.mod`, `Cargo.toml`) or already imported elsewhere in the repository. Check its API against the installed version, not the one you remember |
| A file or path | The directory listing |
| A config key or environment variable | Where it is defined or read (settings files, `.env.example`, config loaders) |
| A route or endpoint | The route table or router registration |
| A database column or table | The schema, model or migrations |

Cite `path:line` for every claim your change or your explanation depends on, so the user can check it in one step.

## When it isn't there

Say so plainly, then say what does exist. For example: "There is no `get_active_users`. `UserRepository` has `get_by_id`, `list_all` and `count` (src/repositories/user.py:14-48)." Then choose one:

- Use the existing, verified interface.
- If you are deliberately introducing the new thing, say so, and define it in the same change so that the call and the definition land together.

Never invent an API, a package name or a file path to fill the gap.

## Saying something is absent needs complete evidence

Only say something does not exist after looking everywhere it could be:

- the class and all of its bases
- the module and its re-exports
- every package in a monorepo that defines that name

Dynamic attributes, generated code, plugins and metaprogramming can hide real members. If your search could have missed something, say "not verified" rather than "does not exist". A confidently wrong claim is worse than an honest "not sure".

## Keep a list of assumptions

Anything you could not verify is an assumption. Label it as one in your plan, for example "Assumption: the cache client is thread-safe; not verified." Verify the assumptions your work depends on before building on them. When evidence contradicts an assumption, stop and revise the plan rather than continuing on top of it.

## Adding a dependency

A dependency is permanent. Before adding one, check whether the project already has something that does the job, such as an HTTP client, a date library, a CLI framework or a test runner. If you still need it:

- Add it to the manifest instead of installing it ad hoc.
- State what it provides that existing code does not.

## When a claim is questioned

When a user, reviewer or tool challenges a claim, check the repository again before answering:

- If the evidence supports you, keep your position and cite it.
- If it doesn't, say so and change course.

Don't reverse yourself without checking, and don't defend a claim without evidence. Once you have answered with evidence, continue with the work instead of debating the same point again.

The user's explicit instructions, repository instructions such as AGENTS.md, and the platform's safety rules take priority over this skill. When one of them conflicts with a step, follow it and say which step you skipped.
