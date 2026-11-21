# FR-GIT-01 portable qualification recipe

This draft preserves nine exact owner-approved source texts and their historical execution identities. Originals are in approved/ and are verified by approved-texts.json. The historical launch scripts remain in that directory as exact text. Use launch.py for this receiving workflow. The draft contains no historical raw Git objects, Git config, reflogs, object inventory, wheel, candidate manifest, runtime inventory or kernel denier.

## Receiving inputs

Use a fresh, independently reviewed registration JSON with the existing tests registration fields. Bind it and the candidate manifest with SHA-256 digests obtained independently of their files. Keep both actual manifests in authorized receiving custody.

| Registration field | Required value |
| --- | --- |
| phase | tests |
| candidate_tree, source_root | The exact reviewed checkout tree and absolute local checkout. Its Git object database and tracked files must be available. For this review the proposed checkout is 4cf0194a3313412511a688e5924f7bb28939d94d. |
| tested_runtime_product_tree, wheel_sha256 | The actual built artifact epoch and wheel digest. The reviewed wheel at its distinct execution epoch is da3f8f074ddbf5a89a9fd6d673f2b39b23b37bbe, SHA-256 db15edf7a6821442ea9b5321ffd3c9ca4d198e704c103cb1f6f044300c034700. Preserve both labels. |
| candidate_manifest, candidate_manifest_sha256 | Absolute path and external SHA-256 of the existing verified package artifact manifest. The manifest supplies the actual wheel, installed target, full installed file map and wheel namespace map. |
| owned_root, output | An absolute caller-owned existing directory and a fresh direct child for this execution. |
| original_eight_registration | Absolute path to approved/fixture/fixture.json. |
| fixture_dir, fixture_declaration_sha256 | The fresh output child git-public/fixtures and the separately preregistered digest of the deterministic declaration. Leave fixture_files empty or omit it. |
| test_nodeids | The existing exact two IDs specified by portable.py. The complete checkout supplies the original test_behavior_identity_history.py configuration helper. |
| file_sha256 | The reviewed absolute regular-file input pins. Include both launcher scripts, the approved-text manifest and all nine approved texts, the candidate manifest and selected installed/runtime inputs, and both tracked test sources with the configuration helper. |

The declaration digest is computed over the UTF-8 text produced from fixture.declare on the approved fixture JSON using json.dumps with indent=2 and allow_nan=False, followed by a final newline. The receiver must preregister that digest before the run. Only the fresh owned execution creates the six-commit repositories, local shallow clone and auxiliary paths.

### External runtime attachment

The existing registration carries a runtime object for the receiving paths. Supply the exact externally attested inputs below. Execution fails if a dependency or its pin is absent. No dependency installation, image pull, checkout modification or package build occurs.

- docker, git, host_python, denier, checker and inventory are actual absolute regular files. Supply each matching *_sha256 value and matching file_sha256 entry. docker_host is the approved local Unix Docker endpoint. image is the existing content-addressed Docker image ID and image_root_layers is its exact ordered layer list.
- mounts contains read-only runtime mounts as source and mount paths. Include the authorized runtime system bindings such as /usr and /etc/alternatives and the selected managed Python runtime. venv is a separate source and mount pair. interpreter is the absolute Python within that mounted environment. The runtime checker and inventory cover their exact bytes, modes, symlinks and image.
- uid, gid and account_home identify the normal preexisting image account. That home and /tmp are empty writable tmpfs boundaries per group. Ensure the Docker UID can write the owned output. No HOME override is supplied.
- The externally supplied checker uses its existing check RECEIPT invocation and binds the sibling runtime-inventory.json at its enclosing qualification root. Its receipt records manifest_sha256, image.id and entries_verified. The external denier uses its existing invocation DENIAL_RECEIPT INTERPRETER ARGUMENTS, installs the real six-syscall filter and execs the program. The worker independently checks IPv4, IPv6 and Unix socket failure. For the approved runtime, denied_errno is ENETUNREACH (101 on Linux).

## Launch

Under the authorized single-job resource boundary, run the preflighted recipe with the two independently approved input SHA-256 values:

```sh
python3 -B launch.py /absolute/receiving-registration.json REGISTRATION_SHA256 CANDIDATE_MANIFEST_SHA256
```

The launcher checks every selected hash before and after, compares the external runtime receipts, and invokes only the three scoped groups. The installed public group generates and verifies the new real six-commit DAG and genuine depth-one local clone, then executes the eight preserved labels. The remaining groups run the same selected Git window and tracked half-configuration preservation cases with independently checked source-first and installed-first origins. The fresh results include raw actual exits, JUnit, complete parity results and socket proofs in the private output. The source checkout is mounted read-only. Both original predicate functions and the extended full-document parity checks are imported from the exact approved texts.

Keep the new fixture internals and raw run output in receiving custody. Review any proposed publication separately. The historical accepted run remains bound to its historical inputs and the portable draft records no new execution result.
