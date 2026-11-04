# Releasing

Production runs the newest `release-X.Y` branch, not main. A fix production needs goes onto that
branch first, as a commit of its own, and is tagged there (`vX.Y.Z`); the release branch is merged
back into main afterwards. Only the fix goes onto a release branch: never merge main into it, and
never commit work in progress there.
