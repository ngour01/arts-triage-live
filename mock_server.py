from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

app = FastAPI(title="Mock DragonSuite")

# 1. Mock the DragonSuite API that returns failing test folders
@app.get("/apis/v1/getCycleRecords")
def get_cycle_records(cycle_id: str = "580", job_status: str = "fail"):
    return {
        "cycle_records": [
            {
                "display_name": "vsan_stretch_cluster",
                "log_location": f"http://localhost:9000/logs/{cycle_id}/vsan_stretch/"
            },
            {
                "display_name": "nsx_routing_suite",
                "log_location": f"http://localhost:9000/logs/{cycle_id}/nsx_routing/"
            }
        ]
    }

# 2. Mock the root folder directory listing (to test folder scraping)
@app.get("/logs/{cycle_id}/{feature}/")
def get_log_dir(cycle_id: str, feature: str):
    html_content = """
    <html><body>
      <a href="test_case_A/">test_case_A/</a><br>
      <a href="test_case_B/">test_case_B/</a><br>
    </body></html>
    """
    return HTMLResponse(content=html_content)

# 3. Mock the sub-folder directory listing
@app.get("/logs/{cycle_id}/{feature}/{test_case}/")
def get_test_dir(cycle_id: str, feature: str, test_case: str):
    html_content = """
    <html><body>
      <a href="stateDump.json.txt">stateDump.json.txt</a><br>
      <a href="testbedSummary.html">testbedSummary.html</a><br>
    </body></html>
    """
    return HTMLResponse(content=html_content)

# 4. Mock the actual JSON log files
@app.get("/logs/{cycle_id}/{feature}/{test_case}/stateDump.json.txt")
def get_state_dump(cycle_id: str, feature: str, test_case: str):
    if "test_case_A" in test_case:
        # Simulate a Product Error (that will also have a PSOD in the HTML)
        return {
            "result": "FAIL", "result_type": "product_error", 
            "error_class": "KernelPanic", "error_message": "Host crashed unexpectedly."
        }
    else:
        # Simulate an Infra Error
        return {
            "result": "FAIL", "result_type": "infra_error", 
            "error_class": "NetworkFault", "error_message": "FAILED TO GET IP from DHCP server."
        }

# 5. Mock the testbedSummary.html files (where PSODs hide)
@app.get("/logs/{cycle_id}/{feature}/{test_case}/testbedSummary.html")
def get_testbed_summary(cycle_id: str, feature: str, test_case: str):
    if "test_case_A" in test_case:
        # Simulate a massive PSOD block
        html = """
        <html><body>
          <div>Some normal logs</div>
          <pre>PSOD: #PF Exception 14 in world 12345
          0x0000000123456789
          0x0000000987654321
          Panic triggered by storage driver</pre>
        </body></html>
        """
        return HTMLResponse(content=html)
    
    return HTMLResponse(content="<html><body><p>Normal execution.</p></body></html>")
