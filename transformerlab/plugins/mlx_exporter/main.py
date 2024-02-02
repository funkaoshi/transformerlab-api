# This plugin exports a model to MLX format so you can interact and train on a MBP with Apple Silicon
import os
import subprocess
import sqlite3
import argparse
import sys
import json
import time

from mlx_lm import convert

root_dir = os.environ.get("LLM_LAB_ROOT_PATH")

# Connect to the LLM Lab database (to update job status details)
db = sqlite3.connect(root_dir + "/workspace/llmlab.sqlite3")

# Get all arguments provided to this script using argparse
parser = argparse.ArgumentParser(description='Convert a model to MLX format.')
parser.add_argument('--output_dir', type=str, help='Directory to save the model in.')
parser.add_argument('--model_name', default='gpt-j-6b', type=str, help='Name of model to export.')
parser.add_argument('--model_architecture', default='hf-causal', type=str, help='Type of model to export.')
parser.add_argument('--output_model_id', default='New Model', type=str, help='Exported ID of the model is also the name of the output directory.')
parser.add_argument('--quant_bits', default='4', type=str, help='Bits per weight for quantization.')
parser.add_argument('--job_id', type=str, help='Job to update in the database.')

args, unknown = parser.parse_known_args()

input_model_id = args.model_name.split("/")[-1]
input_model_architecture = args.model_architecture
output_model_id = args.output_model_id
output_model_dir = args.output_dir

# TODO: Verify that the model uses a supported format
# According to MLX docs (as of Jan 16/24) supported formats are:
# Mistral, Llama, Phi-2

# Directory to run conversion subprocess
plugin_dir = os.path.realpath(os.path.dirname(__file__))

# Use the original model's ID to name the converted model
# Generate a name with a timestamp in case we repeat this process
output_model_architecture = "MLX"
output_model_full_id = f"TransformerLab/{output_model_id}"

# Full directory to output quantized model
output_path = f"{root_dir}/workspace/models/{output_model_dir}"
os.makedirs(output_path)

# Call MLX Convert function
print("Exporting", args.model_name, "to MLX format in", output_path)
export_process = subprocess.run(
    ["python", '-u', '-m',  'mlx_lm.convert', 
        '--hf-path', args.model_name, '--mlx-path', output_path, 
        '-q', '--q-bits', str(args.quant_bits)],
    cwd=plugin_dir,
    capture_output=True
)

# If model create was successful, create an info.json file so this can be read by the system
# and update the job status in the database
if (export_process.returncode == 0):

    model_description = [{
        "model_id": output_model_full_id,
        "model_filename": output_model_dir,
        "name" : output_model_id,
        "local_model": True,
        "json_data" : {
            "uniqueID": output_model_full_id,
            "name": output_model_id,
            "description": f"An MLX modeled generated by TransformerLab based on {args.model_name}",
            "architecture": output_model_architecture,
            "quantization_bits": str(args.quant_bits),
            "huggingface_repo": ""
        }
    }]
    model_description_file = open(f"{output_path}/info.json", "w")
    json.dump(model_description, model_description_file)
    model_description_file.close()

    # update output details in the db
    # first get job details and then add additional fields
    cursor = db.execute("SELECT job_data FROM job WHERE id = ?", (args.job_id,))
    row = cursor.fetchone()
    cursor.close()

    if (row):
        job_data = json.loads(row[0])
        print(job_data["output_model_id"])
        job_data["output_model_id"] = output_model_id
        job_data["output_model_name"] = output_model_id
        job_data["output_model_architecture"] = output_model_architecture
        job_data["output_model_path"] = output_path
        output_job_json = json.dumps(job_data)

        db.execute("UPDATE job \
                   SET job_data = ? \
                   WHERE id = ?",
                   (output_job_json, args.job_id))
        db.commit()

    else:
        print("Failed to update job status. No job with id", args.job_id)
    
    print("Export to MLX completed successfully")

else:
    print("Export to MLX failed. Return code:", export_process.returncode)
