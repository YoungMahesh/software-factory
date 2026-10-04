import modal

# get app id by executing `modal app list`

for sb in modal.Sandbox.list(app_id="<app-id>"):
    print(sb.object_id)
