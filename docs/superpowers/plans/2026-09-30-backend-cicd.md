# Tencent Cloud backend CI/CD

User-approved scope: automate the existing GitHub Actions → SSH → systemd release process, preserving persistent data and configuration.

1. Add a deployment workflow triggered after the existing main-branch check workflow succeeds, with a manual retry path that also runs checks. Serialize production deployments without cancelling an active deployment.
2. Add a root-owned deployment program and a forced-command SSH wrapper. A dedicated SSH account may only submit a commit SHA, archive checksum and archive stream. Validate paths, sizes and file types before extraction. No shell from the submitted archive runs as root.
3. Prebuild the portable package as the application user, back up SQLite and systemd configuration, switch to a versioned release with a systemd override, restart and check the session endpoint. Roll back code/config on failure; retain a protected database backup for explicit recovery (never overwrite live database changes automatically).
4. Test archive validation, successful deployment and failed-health rollback using isolated fixtures. Verify the real server with the existing committed release before enabling automatic deployment.
5. Install a separate deploy account/key, pin the host public key, add the GitHub repository Secret if authenticated access is available, commit and push the workflow, and verify the first Actions run. If Secret administration requires user login, provide the exact remaining step without disclosing private keys in chat.

Vercel remains independently deployed. Backend changes must remain compatible with the previous frontend during rollout; coordinated Vercel promotion is a separate integration and is not claimed here.

## Verification and installation record

- Added missing numerical dependency installation to the existing check workflow and manual deployment checks. Isolated Linux run of the existing suite passed: 153 Python tests, 27 JavaScript tests, portable package check.
- Eight new deployment safeguard tests passed using temporary fixtures, including malformed archives, checksums, code/config rollback and restarting after backup failure.
- Dedicated `aeroblade-deploy` SSH account, forced command and limited sudo rule installed on the existing Tencent host. Arbitrary SSH command rejected in a real connection.
- Real deployment through the restricted key successfully published `df44502fb74a02815de39c1c7e0fabc1f63eae28`, backed up data, restarted and passed session health check.
- GitHub repository Secret `AEROBLADE_DEPLOY_KEY` requires the user's authenticated GitHub settings session; a precise setup request has been sent. First Actions deployment is pending that Secret and workflow publication.
