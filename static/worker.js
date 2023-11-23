import { env, CLIPTextModelWithProjection, AutoTokenizer } from 'https://cdn.jsdelivr.net/npm/@xenova/transformers@2.5.4';

self.postMessage({
    status: 0
});

// Skip local model check
env.allowLocalModels = false;

let text_model = await CLIPTextModelWithProjection.from_pretrained('Xenova/clip-vit-base-patch32');
let tokenizer = await AutoTokenizer.from_pretrained('Xenova/clip-vit-base-patch32');

self.postMessage({
    status: 1
});

// Listen for messages from the main thread
self.addEventListener('message', async (event) => {
    console.log(event)
    let positive_output = null;
    let negative_output = null;

    let text_inputs = tokenizer(event.data.positive, { padding: true, truncation: true });
    let model_output = await text_model(text_inputs);
    console.log(model_output.text_embeds.data);
    positive_output = model_output.text_embeds.data;
    if (event.data.negative!="") {
        let text_inputs = tokenizer(event.data.negative, { padding: true, truncation: true });
        let model_output = await text_model(text_inputs);
        console.log(model_output.text_embeds.data);
        negative_output = model_output.text_embeds.data;
    }

    // Send the output back to the main thread
    self.postMessage({
        status: 1,
        positive: positive_output,
        negative: negative_output,
    });
});