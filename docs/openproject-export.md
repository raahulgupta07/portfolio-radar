# Download all OpenProject projects

Who does this: an OpenProject administrator, or anyone with an API token that can see every project.
Time: about 10 minutes. Nothing in OpenProject is changed: every step only reads.

## Why we need it

Portfolio Radar needs one complete list of OpenProject projects, with owner, status, dates and parent,
so we can check the data, agree the naming rule and set up the nightly sync. The earlier CSV had only
9 columns (name, status, description, created, last activity), with no owner, dates, parent or % complete.

## What you will send back

| File | What it is |
| --- | --- |
| `openproject-projects-<date>.csv` | One row per project. Opens in Excel. |
| `openproject-projects-<date>.json` | The full answer from OpenProject, nothing left out. |

Do not send the token. Send the two files through your normal internal channel.
Both files contain project names and owners, so treat them as internal.

## Step 1: Create a read-only API token

1. Sign in to OpenProject as the service user (or as yourself for this one-off download).
2. Open My account, then Access tokens.
3. Under API, choose Generate, and copy the token. It is shown once.
4. The user must be able to see all projects: an administrator, or a member of every project
   with the permission "View work packages". Archived projects are only visible to administrators.

## Step 2: Run the download script

The script is `scripts/openproject_export.py`. It sends GET requests only and needs Python 3.9 or newer
and nothing else installed.

```
export OPENPROJECT_TOKEN='paste the token here'
python3 scripts/openproject_export.py https://openproject.yourcompany.com --with-dates
```

- Replace the address with your OpenProject address.
- `--with-dates` also reads the earliest start and latest due date of each project's work packages.
  It makes two extra calls per project, so 243 projects take a few minutes. Leave it out for a fast first run.
- The token is read from the environment. It is never typed on the command line and never saved to a file.
- If the script cannot reach OpenProject, run it on a computer on the company network or VPN.

The script prints how many projects it found. Check that the number matches what you see in OpenProject
(Administration, then Projects, with the archived filter on and off).

## Step 3: Check the file

Open the CSV and check:

- The row count matches the project count.
- The `parent_name` column is filled for sub-projects.
- The `status` column is filled. In the earlier export 96 of 243 were blank, which means those projects have no project status set.
- The custom field columns (for example "Project owner") are there and filled. Their labels come from OpenProject.

## Step 4: Answer these questions (one line each)

1. Which column holds the project owner?
2. Which column holds the project status, and what do its values mean (On track, At risk, and so on)?
3. Is a sub-project a project in its own right, or a part of its parent? Which level is a "program"?
4. Do archived projects matter? (The file includes them, marked `active = False`.)
5. Which projects should Radar track? All of them, or only names that start with an approved prefix?
6. What are the approved prefixes, and the date the new naming rule starts?

## Step 5: Switching on the nightly sync (later)

When the file looks right, the same address and token go into the server's secret store
(Admin, then Connections, then OpenProject). Radar then reads the projects every night by itself,
with GET requests only. The token never goes into code, chat or git.

## If something goes wrong

| Message | Meaning |
| --- | --- |
| `answered 401` | The token is wrong or expired. Generate a new one. |
| `answered 403` | The token's user cannot see that data. Use an administrator. |
| `answered 404` | The address is wrong. Use the address you sign in at, with no extra path. |
| `Could not reach` | Network, VPN or firewall. Run it from the company network. |
