from redis_stream_client import redis_client, AUDIO_UPLOADED_STREAM
from transcription_service import assemblyai_transcriber, transcription_complete_producer
import asyncio, json, time


temp_msg = """[Speaker A] You're listening to TED Talks Daily where we bring you new ideas to spark your curiosity every day. I'm your host, Elise Hume. People living across the South Pacific in island nations like Polynesia and Micronesia make up less than 1% of global greenhouse gas emissions and yet they are among the most vulnerable to the threat of climate change. But climate justice advocate Fenton Lutana Tabua doesn't want to feed into the narrative that they are only victims of the climate crisis waiting to be saved. In his 2024 talk, Fenton, a Fiji native himself shares the importance of using community led storytelling to break stereotypes of victimhood.
[Speaker B] Long ago, when I was maybe 10 or 11 years old, I remember my grandfather took me out fishing. We were standing out by the ocean on some rocks and my PA had a spear in his hand and a smile in his eyes, waiting for dinner to swim by. To pass the time, my PA would tell me stories about his old people. That day he told me that we come from a long line of boat builders and fisher folk and that the ocean would always be kind to us. This was my past truth, his story. And his story was what put food on the table for my mother and her siblings. Growing up, the stories that I was surrounded by taught me that I was linked to the ocean and that the ocean was linked to me. Over the years, as I've come to learn about a warming ocean sea level rise and runaway climate impacts, I realized that the very same thing that had nourished my family for generations could now potentially destroy us. This realization has shaped my dedication to building out a truly pacifika led climate movement. Bulavinaca My name is Fenton Utnatombua and I'm from the Fiji Islands. Today I have the absolute privilege to be able to talk to you about the Pacific Climate Warriors. The Pacific Climate warriors are an incredible network of young pacifika people from across the Pacific region and in diaspora communities in Australia, Aotearoa, New Zealand and the United States. The Pacific Climate warriors and the communities that they represent contribute less than 1% to Global Greenhouse gas emissions, yet they are among the most vulnerable to the threats of the climate crisis. Our story as the Pacific Climate warriors began over a decade ago at the Youth Climate Conference, the Global Power Shift in Istanbul, Turkey. It was there that we realized that the only stories folks from outside the Pacific knew about our people was that we were mere victims to this climate crisis, waiting to be saved from our drowning islands. This was of course, untrue. Collectively, right then and there, we decided to break this trend in climate storytelling and instead of only focusing on climate impacts in the Pacific, also show the world what we were doing to fight. We are not drowning, we are fighting became our slogan, our mantra. The shared identity of the Pacific climate warriors was born. And less than a year later, at the largest coal production port in the world in Newcastle, Australia, we paddled out in our traditionally built handmade canoes and blockaded that coal port for a day. In a first of its kind demonstration of that magnitude, we were able to break this victim narrative and build one that reflected the full dignity of our people in the face of this climate crisis. We refused to just be the canary in the coal mines, ready to be sacrificed for the valuable lessons. We knew that we had to be the heroes our communities deserved. And we also knew that we had to retell the world our stories and build our climate narratives. So many of us are being defined by narratives that do not serve us. So many of us let these stories take away our power, rob us of our agency and strip us of our fullest, most authentic selves. That has to change. We are who we are because of the stories we tell ourselves and each other. And we need to get better at telling stories and driving strategies that are bold enough to build a new vision of the futures that we can co create. In order to do that, we need two Climate Leadership and Narrative Leadership. Climate Leadership is specific communities continuing to say no to fossil fuels and yes to climate solutions in whatever spaces we find ourselves, from village town halls all the way up to the United Nations Climate talks. Climate Leadership our partners, allies and collaborators across the majority world creating the conditions necessary for us to voyage towards a Pacific beyond fossil fuels. Climate Leadership are our friends in the Philippines teaching us over zoom how to build backpack size portable solar modules so we have the option to be able to charge our mobile devices, medical supplies as well as turn on a light after a Category 5 cyclone has made landfall on one of our islands. Climate Leadership is about our communities learning about Keyhole Gardens, gardens built above the ground to mitigate saltwater intrusion so our people can grow, consume and redistribute our local and traditional foods. Narrative leadership, on the other hand, is this. It's a community organizer from the Pacific standing here telling you stories about our people at the front lines of this climate crisis. It's a willingness to articulate an alternative way forward that puts people and communities before anything else. Narrative leadership is about telling fuller, more nuanced stories that enable us to become the future ancestors that outcome children can be proud of. Climate Leadership and narrative leadership built and shaped by the most vulnerable communities can and will unlock the futures we all deserve. A future where climate solutions support and empower U.S. indigenous communities to be our most dignified selves. A future where our communities can own and have access to renewable sources of energy, and a future that is ultimately fossil free. It takes all of us doing what we can to be able to co create these futures. And in order to co create these futures that we deserve, we need to break the stories and the strategies that don't serve us anymore and build the ones that do. Beyond just being stewards of our stories, we can also be stewards of our solutions. And thank you very much.
[Speaker A] That was Fenton Lieutenantabua at TED Countdown's Dilemma event in Brussels in 2024. If you're curious about TED's curation, find out more@ted.com curationguidelines and that's it for today's show. TED Talks Daily is part of the TED Audio Collective. This episode was produced and edited by our team, Martha Estefanos, Oliver Friedman, Brian Greene, Lucy Little, Alejandra Salazar and Tonsika Sarmarnivon. It was mixed by Christopher Faizy Bogan. Additional support from Emma Tobner and Daniela Balaurazo. I'm Elise Hu. I'll be back tomorrow with a fresh idea for your feed. Thanks for listening.
[Speaker C] On the TED Radio Hour. In the middle school cafeteria, Ty Toshiro always sat with his equally nerdy buddies.
[Speaker B] The socially awkward kids were the furthest.
[Speaker C] Thing from cool, and he often wondered.
[Speaker B] Why am I so socially awkward? And what am I going to do about that?
[Speaker C] Now? Ty is a psychologist and expert on awkwardness, and he has some answers. So awkward. That's next time on the TED Radio Hour from npr. Subscribe or listen to the TED Radio Hour wherever you get your podcasts"""

async def _handle_message(parsed_data):
    start_time = time.time()
    # delay 5s without blocking the main loop
    # await asyncio.sleep(1)

    # message_txt = temp_msg

    message_txt = await asyncio.to_thread(assemblyai_transcriber.transcribe_audio,parsed_data['file_path'])
    end_time = time.time()
    total_time = end_time-start_time
    print(f"Transcribed and diarized data in {total_time}")

    # now process & emit
    parsed_data["transcript"] = message_txt
    transcription_complete_producer.emit_transcription_completed(parsed_data)
    print(f"✅ Processed and emitted for {parsed_data['file_path']}")

def consume_audio_uploaded(loop):
    print("🎧 Trimming old stream entries and starting consumer...")
    redis_client.xtrim(AUDIO_UPLOADED_STREAM, maxlen=0)
    last_id = "0"  # only listen to *new* messages
    print("👂 Listening for audio_uploaded events...")

    try:
        while True:
            messages = redis_client.xread({AUDIO_UPLOADED_STREAM: last_id}, block=60000, count=1)
            for stream, entries in messages:
                for msg_id, data in entries:
                    print(f"🎧 Received: {data.get('data')}")
                    last_id = msg_id
                    raw_json = data.get('data')
                    if raw_json:
                        try:
                            parsed_data = json.loads(raw_json)
                        except json.JSONDecodeError as e:
                            print("❌ Failed to decode JSON:", e)
                            continue
                        except Exception as e:
                            print(e);
                    else:
                        print("No Data Found")
                        continue
                    asyncio.run_coroutine_threadsafe(
                        _handle_message(parsed_data),
                        loop
                    )

            time.sleep(0.1)
    except asyncio.CancelledError:
        print("🛑 Consumer task cancelled — shutting down gracefully.")


if __name__ == "__main__":
    consume_audio_uploaded()
