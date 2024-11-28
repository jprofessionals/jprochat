const newman = require('newman');
const collectionLink = 'jprochat.postman_collection.json'

function runTest(callback) {
    newman.run({
        collection: collectionLink,
        iterationCount: 1
    },function(error, summary){
          callback(summary)
    });
}

runTest(result => {
    const failures = result.run.failures
    if (failures.length <= 0) {
        console.log("All test ok")
    } else {
        for (let i = 0; i < failures.length; i++) {
            const fault = failures[i]
            const source = fault.source.name
            const errormsg = fault.error.stack
            console.log("Failed test " + source + ": cause " + errormsg)
        }
    }
})