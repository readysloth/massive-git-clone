# massive git clone utility

Get user repos and save them somewhere:

```
GHUSER=user GITHUB_PI_TOKEN=user_token curl "https://api.github.com/users/$GHUSER/repos?access_token=$GITHUB_API_TOKEN" | sed -n '/clone_url/ s!.*https://github.com/\([^"]*\).*!git@github.com:\1!p'
```

Or use baked lists: `better_save_than_sorry.clean.txt` and others.
If you want to download everything, have in mind, that zipped and shallow-cloned repos take ~ 5.7 TB of disk space.

## Requirements

xz, git, python3


## Cloning

You can start cloning with this command: 
```
yes yes | python3 clone.py -mzr better_save_than_sorry.clean.txt
```

**Be aware!** There are some repos, possibly old, that contain https submodules and cloning of these submodules require
authentication. Use [this SO answer](https://stackoverflow.com/a/43022442/11121626) to overcome possible stale in download.


## Unshallowing

You can unshallow previously downloaded repositories with `unshallow.py`.

Possible invocation:
```
find folder_with_zipped_repos -type f | grep '.git.tar.xz$' | python3 unshallow.py -z -o unshallowed -
```
