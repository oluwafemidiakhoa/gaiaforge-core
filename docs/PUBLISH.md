# Publishing a new GaiaForge repository

The project is initialized as a local Git repository. To publish it to your own GitHub account, first create a blank repository named `gaiaforge-core` in GitHub (do not auto-create a README or LICENSE). Then run:

```bash
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/gaiaforge-core.git
git push -u origin main
```

Verify that the repository owner and destination URL are correct before pushing. GitHub credentials should be managed by Git Credential Manager or another secure credential helper; never put a personal access token in a remote URL or commit.

No existing GitHub repository was overwritten in preparation of this artifact.
