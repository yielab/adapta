"""Test script for training API endpoints"""

import requests
import json
import time
from pathlib import Path

BASE_URL = "http://localhost:8000"
TEST_AGENT_ID = "test-agent"


def test_health():
    """Test server health"""
    print("Testing health endpoint...")
    response = requests.get(f"{BASE_URL}/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    print("✅ Health check passed")


def test_create_agent():
    """Test agent creation"""
    print("\nTesting agent creation...")

    data = {
        "name": "Test Training Agent",
        "description": "Agent for testing training pipeline",
        "template": "general",
        "model": "qwen2.5-3b-instruct"
    }

    response = requests.post(f"{BASE_URL}/v1/agents", json=data)

    if response.status_code == 200:
        agent = response.json()
        global TEST_AGENT_ID
        TEST_AGENT_ID = agent["id"]
        print(f"✅ Agent created: {agent['id']}")
        return agent["id"]
    else:
        print(f"⚠️  Agent creation failed: {response.text}")
        return None


def test_upload_training_data(agent_id):
    """Test training data upload"""
    print("\nTesting training data upload...")

    # Create test JSONL data
    training_data = [
        {
            "messages": [
                {"role": "user", "content": "What is Python?"},
                {"role": "assistant", "content": "Python is a high-level programming language."}
            ]
        },
        {
            "messages": [
                {"role": "user", "content": "What is JavaScript?"},
                {"role": "assistant", "content": "JavaScript is a web programming language."}
            ]
        },
        {
            "messages": [
                {"role": "user", "content": "What is TypeScript?"},
                {"role": "assistant", "content": "TypeScript is a typed superset of JavaScript."}
            ]
        }
    ]

    # Write to temporary file
    test_file = Path("/tmp/test_training.jsonl")
    with open(test_file, "w") as f:
        for item in training_data:
            f.write(json.dumps(item) + "\n")

    # Upload
    with open(test_file, "rb") as f:
        files = {"file": ("test_training.jsonl", f, "application/x-ndjson")}
        response = requests.post(
            f"{BASE_URL}/v1/agents/{agent_id}/training/data",
            files=files
        )

    if response.status_code == 200:
        result = response.json()
        print(f"✅ Dataset uploaded: {result['name']}")
        print(f"   Examples: {result['num_examples']}, Valid: {result['is_valid']}")
        return result["name"]
    else:
        print(f"❌ Upload failed: {response.text}")
        return None


def test_list_datasets(agent_id):
    """Test listing training datasets"""
    print("\nTesting dataset listing...")

    response = requests.get(f"{BASE_URL}/v1/agents/{agent_id}/training/data")

    if response.status_code == 200:
        datasets = response.json()
        print(f"✅ Found {len(datasets)} datasets")
        for ds in datasets:
            print(f"   - {ds['name']}: {ds['num_examples']} examples")
        return datasets
    else:
        print(f"❌ List failed: {response.text}")
        return []


def test_start_training(agent_id, dataset_name):
    """Test starting a training job"""
    print("\nTesting training job creation...")

    data = {
        "base_model": "qwen2.5-3b-instruct",
        "dataset_name": dataset_name,
        "adapter_name": "test_adapter_v1",
        "config": {
            "num_epochs": 1,  # Just 1 epoch for testing
            "batch_size": 2,
            "learning_rate": 0.0002,
            "use_qlora": True
        }
    }

    response = requests.post(
        f"{BASE_URL}/v1/agents/{agent_id}/training/jobs",
        json=data
    )

    if response.status_code == 200:
        job = response.json()
        print(f"✅ Training job created: {job['job_id']}")
        print(f"   State: {job['state']}, Progress: {job['progress']}")
        return job["job_id"]
    else:
        print(f"❌ Training job creation failed: {response.text}")
        return None


def test_job_status(agent_id, job_id):
    """Test getting job status"""
    print("\nTesting job status...")

    response = requests.get(
        f"{BASE_URL}/v1/agents/{agent_id}/training/jobs/{job_id}"
    )

    if response.status_code == 200:
        status = response.json()
        print(f"✅ Job status:")
        print(f"   State: {status['state']}")
        print(f"   Progress: {status['progress'] * 100:.1f}%")
        print(f"   Current step: {status['current_step']}/{status['total_steps']}")
        if status.get('current_loss'):
            print(f"   Current loss: {status['current_loss']:.4f}")
        if status.get('error_message'):
            print(f"   Error: {status['error_message']}")
        return status
    else:
        print(f"❌ Status check failed: {response.text}")
        return None


def test_list_jobs(agent_id):
    """Test listing all jobs"""
    print("\nTesting job listing...")

    response = requests.get(f"{BASE_URL}/v1/agents/{agent_id}/training/jobs")

    if response.status_code == 200:
        jobs = response.json()
        print(f"✅ Found {len(jobs)} jobs")
        for job in jobs:
            print(f"   - {job['job_id']}: {job['state']} ({job['progress'] * 100:.1f}%)")
        return jobs
    else:
        print(f"❌ List failed: {response.text}")
        return []


def test_queue_status():
    """Test queue status"""
    print("\nTesting queue status...")

    response = requests.get(f"{BASE_URL}/v1/training/queue")

    if response.status_code == 200:
        status = response.json()
        print(f"✅ Queue status:")
        print(f"   Total jobs: {status['total_jobs']}")
        print(f"   Running: {status['running']}")
        print(f"   Queued: {status['queued']}")
        print(f"   Completed: {status['completed']}")
        print(f"   Failed: {status['failed']}")
        return status
    else:
        print(f"❌ Queue status failed: {response.text}")
        return None


def monitor_training(agent_id, job_id, max_wait=300):
    """Monitor training progress"""
    print(f"\nMonitoring training job {job_id}...")
    print("This may take a while. Press Ctrl+C to stop monitoring.\n")

    start_time = time.time()

    try:
        while time.time() - start_time < max_wait:
            status = test_job_status(agent_id, job_id)

            if status:
                if status['state'] in ['completed', 'failed', 'cancelled']:
                    print(f"\n✅ Training finished: {status['state']}")
                    return status

            time.sleep(5)
            print("---")

        print(f"\n⏱️  Timeout after {max_wait}s")
        return None

    except KeyboardInterrupt:
        print("\n⏸️  Monitoring stopped")
        return None


def run_all_tests():
    """Run all tests"""
    print("=" * 60)
    print("Brain From Cero - Training API Tests")
    print("=" * 60)

    try:
        # Test health
        test_health()

        # Create test agent
        agent_id = test_create_agent()
        if not agent_id:
            print("\n❌ Cannot continue without agent")
            return

        # Upload training data
        dataset_name = test_upload_training_data(agent_id)
        if not dataset_name:
            print("\n❌ Cannot continue without dataset")
            return

        # List datasets
        test_list_datasets(agent_id)

        # Start training
        job_id = test_start_training(agent_id, dataset_name)
        if not job_id:
            print("\n❌ Cannot continue without job")
            return

        # Check job status immediately
        test_job_status(agent_id, job_id)

        # List all jobs
        test_list_jobs(agent_id)

        # Check queue status
        test_queue_status()

        # Monitor training (optional)
        print("\n" + "=" * 60)
        response = input("Monitor training progress? (y/n): ")
        if response.lower() == 'y':
            monitor_training(agent_id, job_id)

        print("\n" + "=" * 60)
        print("Tests completed!")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    run_all_tests()
