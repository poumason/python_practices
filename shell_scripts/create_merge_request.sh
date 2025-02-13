token=""
project_id=""
host="https://gitlab.com/api/v4/projects/$project_id/merge_requests"

echo $token
echo $project_id
echo $host

id="Pou"
source_branch="pou/dev"
target_branch="main"
payload='{ "id": "'"$id"'", 
             "source_branch": "'"$source_branch"'", 
             "target_branch": "'"$target_branch"'", 
             "title": "test" }'

echo $payload

curl -X POST \
    --header "Authorization: Bearer $token" \
     --header "Content-Type: application/json" \
     --data "$payload" \
     $host


# curl --header "PRIVATE-TOKEN: glpat-6jzwm5Hxqs8QCQfV6UrP" \
#   --url "https://gitlab.example.com/api/v4/projects/56958177/merge_requests"

